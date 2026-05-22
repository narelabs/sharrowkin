"""
RLD Real LLM Benchmark: Phi-3.5-mini + Neural Encoder
======================================================
Compares Vanilla vs RLD-augmented reasoning on math problems.
"""
import sys, os, time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dsm/src")))

from rld.core import RecursiveLatentDNA
from dsm.embedding import HashEmbeddingModel


class NeuralEmb:
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self._m = SentenceTransformer("all-MiniLM-L6-v2")
        self.dim = self._m.get_embedding_dimension()
    def encode(self, text):
        return self._m.encode(text, normalize_embeddings=True).tolist()


def load_model():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    name = "Qwen/Qwen2.5-1.5B-Instruct"
    print(f"Loading {name}...")
    t0 = time.time()

    tokenizer = AutoTokenizer.from_pretrained(name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        name, torch_dtype=torch.float32, device_map="cpu", trust_remote_code=True
    )
    print(f"Loaded in {time.time()-t0:.1f}s")
    return model, tokenizer


def ask(model, tokenizer, prompt, max_tokens=200):
    import torch
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
    return tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()


QUESTIONS = [
    {
        "q": "A store sells notebooks for $3 each. If you buy 5 or more, you get 20% off the total. How much do 7 notebooks cost?",
        "answer": "16.8",
        "alt": ["16.80", "$16.8", "$16.80"],
    },
    {
        "q": "If x + 7 = 15, what is the value of 3x - 2?",
        "answer": "22",
        "alt": ["22.0"],
    },
    {
        "q": "A train travels 120 km in 2 hours, then 90 km in 1.5 hours. What is the average speed for the entire trip in km/h?",
        "answer": "60",
        "alt": ["60.0", "60 km/h"],
    },
    {
        "q": "Maria has 24 cookies. She gives 1/3 to her brother, then eats 4 herself. How many cookies are left?",
        "answer": "12",
        "alt": ["12.0"],
    },
    {
        "q": "A water tank is 1/4 full. After adding 15 liters of water, it becomes 1/2 full. What is the total capacity of the tank in liters?",
        "answer": "60",
        "alt": ["60.0", "60 liters"],
    },
    {
        "q": "If 5 machines can make 5 widgets in 5 minutes, how many minutes does it take 100 machines to make 100 widgets?",
        "answer": "5",
        "alt": ["5 minutes", "5.0"],
    },
    {
        "q": "The price of a shirt was $40. It was increased by 25%, then decreased by 20%. What is the final price?",
        "answer": "40",
        "alt": ["40.0", "$40", "$40.00"],
    },
    {
        "q": "A farmer has 15 sheep. All but 8 die. How many sheep are left?",
        "answer": "8",
        "alt": ["8.0", "eight"],
    },
    {
        "q": "A father is 3 times as old as his son. In 12 years, he will be 2 times as old as his son. How old is the son now?",
        "answer": "12",
        "alt": ["12.0", "12 years old"],
    },
    {
        "q": "What is 15% of 200 plus 25% of 80?",
        "answer": "50",
        "alt": ["50.0"],
    },
]


def check_answer(response, item):
    resp = response.lower().replace(",", "")
    targets = [item["answer"]] + item.get("alt", [])
    return any(t.lower() in resp for t in targets)


def main():
    print("=" * 60)
    print("  RLD + Phi-3.5-mini: Real LLM Benchmark")
    print("=" * 60)

    # Setup RLD with neural encoder
    print("\n[1] Setting up RLD with neural encoder...")
    enc = NeuralEmb()
    rld = RecursiveLatentDNA(
        storage_path=".rld_phi_bench.json",
        embedding_model=enc,
        activation_threshold=0.20,
    )

    # Train reasoning genes
    rld.observe(
        task="Solve multi-step math word problems requiring arithmetic and percentages",
        states=["parse problem", "identify quantities", "apply operations step by step", "verify result"],
        actions=["extract_numbers", "compute_intermediate", "apply_discount_or_tax", "final_check"],
        final_answer="Break into steps: identify values, compute each operation, verify",
        success=True, utility=1.0,
    )
    rld.observe(
        task="Solve algebraic equations by isolating variables",
        states=["identify variable", "isolate on one side", "compute value", "substitute back"],
        actions=["parse_equation", "subtract_constants", "divide_coefficient", "verify_substitution"],
        final_answer="Solve for variable, then substitute into expression",
        success=True, utility=1.0,
    )
    print(f"   Trained {len(rld.genes)} genes")

    # Load LLM
    print("\n[2] Loading LLM...")
    model, tokenizer = load_model()

    # Run benchmark
    print("\n[3] Running benchmark...\n")
    v_correct = 0
    r_correct = 0

    for i, item in enumerate(QUESTIONS, 1):
        q = item["q"]
        print(f"  Q{i}: {q[:65]}...")

        # Vanilla
        v_prompt = f"Solve step by step. Give the final numerical answer on the last line.\n\n{q}"
        v_ans = ask(model, tokenizer, v_prompt)
        v_ok = check_answer(v_ans, item)
        if v_ok: v_correct += 1

        # RLD
        ctx = rld.active_context(q, threshold=0.15)
        genes_text = ctx.context_text if ctx.activated else ""
        r_prompt = f"{genes_text}\n\nUsing the reasoning approach above, solve step by step. Give the final numerical answer on the last line.\n\n{q}" if genes_text else v_prompt
        r_ans = ask(model, tokenizer, r_prompt)
        r_ok = check_answer(r_ans, item)
        if r_ok: r_correct += 1

        print(f"      Vanilla: {'PASS' if v_ok else 'FAIL'} | {v_ans[:70]}")
        print(f"      RLD:     {'PASS' if r_ok else 'FAIL'} | {r_ans[:70]}")
        print(f"      Expected: {item['answer']} | Genes: {len(ctx.activated)}")
        print()

    n = len(QUESTIONS)
    print("=" * 60)
    print(f"  RESULTS")
    print(f"  Vanilla:  {v_correct}/{n} = {v_correct/n*100:.0f}%")
    print(f"  RLD:      {r_correct}/{n} = {r_correct/n*100:.0f}%")
    diff = r_correct - v_correct
    print(f"  Delta:    {'+' if diff >= 0 else ''}{diff}")
    print("=" * 60)


if __name__ == "__main__":
    main()
