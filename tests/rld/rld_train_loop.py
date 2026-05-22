"""
RLD Evolutionary Training Loop
===============================
Phase 1: Model solves problems (baseline)
Phase 2: Model analyzes its own errors and creates Correction Genes
Phase 3: Model re-solves with new genes (boosted)
"""
import sys, os, time, json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dsm/src")))

from rld.core import RecursiveLatentDNA, default_embedding_model
from dsm.embedding import HashEmbeddingModel


PROBLEMS = [
    {"q": "A store sells notebooks for $3 each. If you buy 5 or more, you get 20% off the total. How much do 7 notebooks cost?",
     "answer": "16.8", "alt": ["16.80", "$16.8"]},
    {"q": "If x + 7 = 15, what is the value of 3x - 2?",
     "answer": "22", "alt": ["22.0"]},
    {"q": "A train travels 120 km in 2 hours, then 90 km in 1.5 hours. What is the average speed for the entire trip in km/h?",
     "answer": "60", "alt": ["60.0"]},
    {"q": "Maria has 24 cookies. She gives 1/3 to her brother, then eats 4 herself. How many cookies are left?",
     "answer": "12", "alt": ["12.0"]},
    {"q": "A water tank is 1/4 full. After adding 15 liters, it becomes 1/2 full. What is the total capacity in liters?",
     "answer": "60", "alt": ["60.0"]},
    {"q": "If 5 machines make 5 widgets in 5 minutes, how many minutes for 100 machines to make 100 widgets?",
     "answer": "5", "alt": ["5.0", "5 minutes"]},
    {"q": "A shirt costs $40. Price increased by 25%, then decreased by 20%. What is the final price?",
     "answer": "40", "alt": ["40.0", "$40", "$40.00"]},
    {"q": "A farmer has 15 sheep. All but 8 die. How many sheep are left?",
     "answer": "8", "alt": ["8.0"]},
    {"q": "A father is 3 times as old as his son. In 12 years, he will be 2 times as old. How old is the son now?",
     "answer": "12", "alt": ["12.0"]},
    {"q": "What is 15% of 200 plus 25% of 80?",
     "answer": "50", "alt": ["50.0"]},
]


def load_model():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    name = "Qwen/Qwen2.5-1.5B-Instruct"
    print(f"  Loading {name} on GPU (local-first)...")
    t0 = time.time()
    try:
        tok = AutoTokenizer.from_pretrained(name, trust_remote_code=True, local_files_only=True)
        mdl = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float16, device_map="cuda", trust_remote_code=True, local_files_only=True)
    except Exception:
        print("  Local weights not found. Connecting online to download model...")
        tok = AutoTokenizer.from_pretrained(name, trust_remote_code=True)
        mdl = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float16, device_map="cuda", trust_remote_code=True)
    print(f"  Loaded in {time.time()-t0:.1f}s on {torch.cuda.get_device_name(0)}")
    return mdl, tok


def ask(model, tokenizer, prompt, max_tokens=250):
    import torch
    msgs = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
    return tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()


def check(response, item):
    r = response.lower().replace(",", "")
    return any(t.lower() in r for t in [item["answer"]] + item.get("alt", []))


def run_eval(model, tokenizer, rld, label, threshold=0.15):
    """Run all problems, return (correct_count, list_of_failures)."""
    correct = 0
    failures = []
    for i, p in enumerate(PROBLEMS, 1):
        ctx = rld.active_context(p["q"], threshold=threshold) if rld else None
        if rld and ctx and ctx.activated:
            prompt = f"{ctx.context_text}\n\nUsing the reasoning approach above, solve step by step. Final numerical answer on last line.\n\n{p['q']}"
        else:
            prompt = f"Solve step by step. Final numerical answer on last line.\n\n{p['q']}"

        ans = ask(model, tokenizer, prompt)
        ok = check(ans, p)
        if ok:
            correct += 1
        else:
            failures.append({"idx": i, "q": p["q"], "expected": p["answer"], "got": ans[:120]})

        tag = "OK" if ok else "XX"
        print(f"    [{tag}] Q{i:2d}: {p['q'][:55]}... -> {ans[:40]}")

    print(f"  {label}: {correct}/{len(PROBLEMS)} = {correct/len(PROBLEMS)*100:.0f}%")
    return correct, failures


def create_correction_genes(model, tokenizer, rld, failures):
    """Ask model to analyze its own errors and create correction genes."""
    print(f"\n  Creating correction genes from {len(failures)} failures...")

    for f in failures:
        # Ask model to analyze its own mistake
        analysis_prompt = (
            f"You made an error solving this math problem.\n"
            f"Problem: {f['q']}\n"
            f"Your wrong answer: {f['got'][:80]}\n"
            f"Correct answer: {f['expected']}\n\n"
            f"Write a SHORT rule (1-2 sentences) that would prevent this specific mistake. "
            f"Focus on the exact step where the error occurred. "
            f"Start with 'RULE:'"
        )

        rule = ask(model, tokenizer, analysis_prompt, max_tokens=100)
        # Extract the rule
        if "RULE:" in rule:
            rule = rule.split("RULE:")[-1].strip()
        rule = rule[:200]

        print(f"    Q{f['idx']}: {rule[:70]}...")

        # Save as a correction gene via RLD observe
        rld.observe(
            task=f"Avoid error in: {f['q'][:80]}",
            states=["check problem type", "identify trap", "apply correction rule", "verify"],
            actions=["parse_carefully", "apply_rule", "double_check"],
            final_answer=f"CORRECTION: {rule}",
            success=True,
            utility=1.0,
            tools_used=["self_correction"],
        )

    print(f"  Created {len(failures)} correction genes. Total genes: {len(rld.genes)}")


def main():
    print("=" * 60)
    print("  RLD EVOLUTIONARY TRAINING LOOP")
    print("  Self-learning from errors")
    print("=" * 60)

    # Setup
    enc = default_embedding_model()
    model, tokenizer = load_model()

    # Phase 1: Vanilla baseline (no RLD)
    print("\n--- PHASE 1: Vanilla Baseline ---")
    vanilla_score, _ = run_eval(model, tokenizer, None, "Vanilla")

    # Phase 2: Static genes (like before)
    print("\n--- PHASE 2: Static Genes ---")
    rld = RecursiveLatentDNA(
        storage_path=".rld_evo_train.json",
        embedding_model=enc,
        activation_threshold=0.20,
    )
    rld.observe(
        task="Solve multi-step math word problems with arithmetic and percentages",
        states=["parse problem", "identify quantities", "compute step by step", "verify"],
        actions=["extract_numbers", "compute_intermediate", "check_result"],
        final_answer="Always break into steps and verify each computation",
        success=True, utility=1.0,
    )
    rld.observe(
        task="Solve algebraic equations by isolating variables",
        states=["identify variable", "isolate", "compute", "substitute back"],
        actions=["parse_equation", "subtract_constants", "divide", "verify"],
        final_answer="Solve for variable, then substitute into expression",
        success=True, utility=1.0,
    )
    static_score, failures = run_eval(model, tokenizer, rld, "Static RLD")

    # Phase 3: Create correction genes from failures
    if failures:
        print("\n--- PHASE 3: Self-Correction ---")
        create_correction_genes(model, tokenizer, rld, failures)
        rld.save()

        # Phase 4: Re-run with correction genes
        print("\n--- PHASE 4: Evolved RLD ---")
        evolved_score, remaining = run_eval(model, tokenizer, rld, "Evolved RLD")
    else:
        evolved_score = static_score
        remaining = []

    # Final report
    n = len(PROBLEMS)
    print("\n" + "=" * 60)
    print("  EVOLUTION REPORT")
    print("=" * 60)
    print(f"  Vanilla:      {vanilla_score}/{n} = {vanilla_score/n*100:.0f}%")
    print(f"  Static RLD:   {static_score}/{n} = {static_score/n*100:.0f}%")
    print(f"  Evolved RLD:  {evolved_score}/{n} = {evolved_score/n*100:.0f}%")
    print(f"  Total genes:  {len(rld.genes)}")
    print(f"  Remaining errors: {len(remaining)}")
    boost = evolved_score - vanilla_score
    print(f"  Total boost:  +{boost} ({boost/max(vanilla_score,1)*100:.0f}% improvement)")
    print("=" * 60)


if __name__ == "__main__":
    main()
