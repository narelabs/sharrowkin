"""
RLD Evolution Validation - FULL BATCH (92 Genes)
Re-tests all failure cases that have corresponding correction genes.
"""
import sys, os, json, re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from rld.core import RecursiveLatentDNA
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

def extract_answer(text):
    match = re.search(r"####\s*(-?\d+)", text)
    if match: return match.group(1)
    nums = re.findall(r"-?\d+", text.replace(",", ""))
    return nums[-1] if nums else None

def load_data():
    with open("gsm8k_test.json", "r") as f:
        return json.load(f)

def main():
    print("=" * 60)
    print("  RLD VALIDATION PHASE - 92 GENES TEST")
    print("=" * 60)

    # Initialize RLD and find which tasks we have genes for
    rld = RecursiveLatentDNA(storage_path=".rld_gsm8k_knowledge.json", activation_threshold=0.1)
    
    # Extract task indices from trajectories
    evolved_indices = []
    for traj_id in rld.trajectories.keys():
        # Trajectories are stored with task name "GSM8K_idx"
        traj = rld.trajectories[traj_id]
        match = re.search(r"GSM8K_(\d+)", traj.task)
        if match:
            evolved_indices.append(int(match.group(1)))
    
    evolved_indices = sorted(list(set(evolved_indices)))
    print(f"Testing RLD on {len(evolved_indices)} evolved failure cases...")

    ds = load_data()
    name = "Qwen/Qwen2.5-1.5B-Instruct"
    tokenizer = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.float16, device_map="cuda")

    fixed = 0
    results = []

    for i, f_idx in enumerate(evolved_indices):
        item = ds[f_idx]
        q = item["question"]
        target = extract_answer(item["answer"])

        ctx = rld.active_context(q)
        prompt = f"{ctx.context_text}\n\nQuestion: {q}\nAnswer: Let's think step by step."
        
        inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=300, do_sample=False)
        
        gen_text = tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        ans = extract_answer(gen_text)
        is_ok = (ans == target)
        if is_ok: fixed += 1

        status = "FIXED" if is_ok else "FAILED"
        print(f"[{i+1}/{len(evolved_indices)}] Task {f_idx}: {status} | Genes: {len(ctx.activated)}")

    print("\n" + "=" * 60)
    print(f"  VALIDATION COMPLETE.")
    print(f"  TOTAL TESTED: {len(evolved_indices)}")
    print(f"  FIXED: {fixed}")
    print(f"  RECOVERY RATE: {(fixed/len(evolved_indices)):.1%}" if evolved_indices else "N/A")
    print("=" * 60)

if __name__ == "__main__":
    main()
