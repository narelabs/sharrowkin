"""
RLD + DPM Hybrid GSM8K Benchmark (Ultra-Fast: No Vanilla Overhead)
Combines software context memory (RLD) inside official Chat Template with hardware adapter memory (DPM).
"""
import sys
import os

# Принудительно отключаем запросы к HuggingFace в интернет (100% Offline Mode)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import time
import json
import re
from pathlib import Path
import torch
from transformers import AutoTokenizer

# Добавляем пути к исходникам Cortex-1
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(ROOT_DIR / "projects" / "nare_dpm_cortex" / "src"))
sys.path.append(str(ROOT_DIR / "modules" / "rld" / "src"))
from cortex_model import NARECortexModel
from rld.core import RecursiveLatentDNA

def extract_answer(text):
    match = re.search(r"####\s*(-?\d+)", text)
    if match: return match.group(1)
    
    # Сначала удаляем все десятичные части (например, .00 или .5), чтобы они не дробились на два числа
    clean_text = re.sub(r"\.\d+", "", text)
    
    # Теперь извлекаем целые числа
    nums = re.findall(r"-?\d+", clean_text.replace(",", ""))
    return nums[-1] if nums else None

def load_data():
    path = str(ROOT_DIR / "gsm8k_test.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    print("=" * 60)
    print("  ULTRA-FAST HYBRID (RLD + DPM) GSM8K BENCHMARK")
    print("=" * 60)

    results_file = str(ROOT_DIR / "gsm8k_results.jsonl")
    processed_ids = set()
    hybrid_correct = 0

    if os.path.exists(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                    processed_ids.add(data["idx"])
                    # В гибридном режиме мы трекаем только успехи гибрида (r_ok)
                    if data["r_ok"]: hybrid_correct += 1
                except Exception:
                    continue
        print(f"Resuming from {len(processed_ids)} tasks.")
        print(f"Current Hybrid Correct Answers: {hybrid_correct}")

    ds = load_data()
    model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    print("[*] Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    
    print("[*] Initializing NARECortexModel Core...")
    model = NARECortexModel(base_model_name=model_name, memory_dim=128, num_adapters=16)
    
    # Загружаем DPM-веса
    weights_path = ROOT_DIR / "projects" / "nare_dpm_cortex" / "models" / "cortex_v1.pt"
    if weights_path.exists():
        print(f"[+] Loading trained DPM weights from {weights_path.name}...")
        model.load_state_dict(torch.load(weights_path))
    else:
        print("[!] Trained DPM weights not found!")
        
    model = model.half().to(device)
    model.eval()

    # Инициализация софтверной RLD памяти
    rld = RecursiveLatentDNA(storage_path=str(ROOT_DIR / ".rld_gsm8k_knowledge.json"), activation_threshold=0.25)
    rld.observe(task="Solve math", states=["read", "solve"], actions=["solve"], final_answer="####", success=True, utility=1.0)

    print("\nStarting ultra-fast RLD + DPM hybrid inference loop...")
    for i, item in enumerate(ds):
        if i in processed_ids: continue
        
        q = item["question"]
        target = extract_answer(item["answer"])

        # 1. Сбор софтверного контекста из RLD
        ctx = rld.active_context(q)
        
        # Внедряем RLD-память прямо в Системный промпт Chat-Template!
        system_content = "You are a helpful assistant. Solve the math problem step by step. End your response with the final numerical answer after '#### '."
        if ctx.context_text:
            system_content += f"\n\nUseful Context from past similar tasks:\n{ctx.context_text}"

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": q}
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(device)

        # 2. Инференс на чистом DPM с активированным математическим адаптером
        memory_state = torch.zeros(1, 128, dtype=torch.float16, device=device)
        memory_state[0, 6] = 5.0  # Сигнал активации эксперта по логике/математике!

        with torch.no_grad():
            out = model.generate(
                input_ids=inputs.input_ids,
                memory_state=memory_state,
                max_new_tokens=256,
                pad_token_id=tokenizer.eos_token_id,
                temperature=0.1,
                attention_mask=inputs.attention_mask
            )
        
        response = tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        ans = extract_answer(response)
        ok = ans == target

        if ok: hybrid_correct += 1

        total_processed = len(processed_ids) + 1
        print(f"[{i+1}/{len(ds)}] Q: {q[:50]}...")
        print(f"  [Hybrid] Answer: {ans} | Target: {target} | {'✅' if ok else '❌'}")
        print(f"  [i] Total Hybrid Accuracy: {hybrid_correct/total_processed:.1%} ({hybrid_correct}/{total_processed})")

        # Логируем результат (v_ok = False, т.к. ваниль не гоняем, r_ok = наш гибрид)
        with open(results_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "idx": i, 
                "v_ok": False, 
                "r_ok": ok, 
                "genes": len(ctx.activated)
            }) + "\n")
            
        processed_ids.add(i)

if __name__ == "__main__":
    main()
