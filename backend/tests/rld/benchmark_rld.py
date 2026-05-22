"""
RLD Real Benchmark: Neural Encoder + Qwen LLM
==============================================
Phase 1: Test retrieval precision with sentence-transformers
Phase 2: Test actual reasoning improvement with Qwen model
"""
import sys, os, asyncio, time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dsm/src")))

from rld.core import RecursiveLatentDNA


class SentenceTransformerEmbedding:
    """Real neural embedding - defined inline to avoid shadowed dsm import."""
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def encode(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()


# ============================================================
# PHASE 1: Retrieval with real embeddings
# ============================================================
async def phase1_retrieval():
    print("=" * 55)
    print("  PHASE 1: Retrieval with Neural Embeddings")
    print("=" * 55)

    t0 = time.time()
    encoder = SentenceTransformerEmbedding("all-MiniLM-L6-v2")
    print(f"  Encoder loaded in {time.time()-t0:.1f}s (dim={encoder.dim})")

    rld = RecursiveLatentDNA(
        storage_path=".rld_real_bench.json",
        embedding_model=encoder,
        activation_threshold=0.25,
    )

    # Train 3 distinct genes
    rld.observe(
        task="Solve algebraic equations by isolating variables and simplifying",
        states=["identify unknown variable", "move constants to other side", "divide by coefficient"],
        actions=["parse_equation", "transpose_terms", "simplify_result"],
        final_answer="x = (b - c) / a",
        success=True, utility=0.95,
        tools_used=["symbolic_solver"],
    )

    rld.observe(
        task="Debug Python runtime errors by analyzing tracebacks and fixing code",
        states=["read error type and message", "locate file and line number", "inspect variable state"],
        actions=["read_traceback", "open_source_file", "add_debug_print", "apply_fix"],
        final_answer="Fixed TypeError by converting string to integer before arithmetic",
        success=True, utility=0.90,
        tools_used=["debugger", "code_editor"],
    )

    rld.observe(
        task="Analyze tabular datasets to discover statistical patterns and outliers",
        states=["load CSV into dataframe", "compute descriptive statistics", "generate visualizations"],
        actions=["pandas_read_csv", "df_describe", "plot_distribution", "detect_outliers"],
        final_answer="Identified 3 outlier records exceeding 2 standard deviations from mean",
        success=True, utility=0.88,
        tools_used=["pandas", "matplotlib", "scipy"],
    )

    print(f"  Trained {len(rld.genes)} genes\n")

    # Test cases
    tests = [
        ("How do I solve 2x + 3 = 15?",                   "algebra",   "Math -> Math gene"),
        ("My code throws AttributeError on line 55",       "debug",     "Debug -> Debug gene"),
        ("Show me trends in this CSV sales data",          "dataset",   "Data -> Data gene"),
        ("What is the capital of France?",                 None,        "Irrelevant -> No gene"),
        ("Rearrange this formula to find y",               "algebra",   "Math transfer"),
        ("IndexError: list index out of range in parser",  "debug",     "Debug transfer"),
        ("Calculate mean and variance of temperature data", "statistic", "Data transfer"),
    ]

    correct = 0
    total = len(tests)

    for query, keyword, label in tests:
        ctx = rld.active_context(query, threshold=0.25)

        if keyword is None:
            ok = len(ctx.activated) == 0
            tag = "PASS" if ok else f"WEAK ({len(ctx.activated)} fp)"
        else:
            matched = any(
                keyword.lower() in (g.gene.task_context + " " + g.gene.transformation_delta + " " + " ".join(g.gene.reasoning_steps) + " " + " ".join(g.gene.trigger_terms)).lower()
                for g in ctx.activated
            )
            ok = matched
            tag = "PASS" if ok else "FAIL"

        if ok: correct += 1
        top = f"p={ctx.activated[0].probability:.3f}" if ctx.activated else "none"
        n = len(ctx.activated)
        print(f"  [{tag:6s}] {label:20s} | activated={n} {top} | q={query[:45]}")

    precision = correct / total * 100
    print(f"\n  Retrieval Precision: {correct}/{total} = {precision:.1f}%")
    rld.save()
    return rld, precision


# ============================================================
# PHASE 2: Actual LLM test with Qwen
# ============================================================
async def phase2_qwen(rld: RecursiveLatentDNA):
    print("\n" + "=" * 55)
    print("  PHASE 2: Qwen LLM + RLD Reasoning Test")
    print("=" * 55)

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    except ImportError:
        print("  SKIP: transformers/torch not available")
        return

    model_name = "Qwen/Qwen3-0.6B"
    print(f"  Loading {model_name}...")
    t0 = time.time()

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float32,
        device_map="cpu",
        trust_remote_code=True,
    )
    print(f"  Model loaded in {time.time()-t0:.1f}s\n")

    def ask_qwen(prompt: str, max_tokens: int = 150) -> str:
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
                temperature=1.0,
            )
        return tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()

    # Math questions where reasoning genes should help
    questions = [
        {
            "q": "A store sells notebooks for $3 each. If you buy 5 or more, you get 20% off. How much do 7 notebooks cost?",
            "answer": "16.8",
        },
        {
            "q": "A car drives 120 km in 2 hours, then 90 km in 1.5 hours. What is the average speed for the entire trip?",
            "answer": "60",
        },
        {
            "q": "If x + 7 = 15, what is 3x - 2?",
            "answer": "22",
        },
    ]

    vanilla_correct = 0
    rld_correct = 0

    for item in questions:
        q = item["q"]
        expected = item["answer"]

        # Vanilla
        vanilla_prompt = f"Solve this step by step. Give only the final number.\n\nQuestion: {q}\nAnswer:"
        vanilla_ans = ask_qwen(vanilla_prompt)

        # RLD-augmented
        ctx = rld.active_context(q, threshold=0.15)
        rld_prompt = f"{ctx.context_text}\n\nUsing the reasoning genes above, solve this step by step. Give only the final number.\n\nQuestion: {q}\nAnswer:"
        rld_ans = ask_qwen(rld_prompt)

        v_ok = expected in vanilla_ans
        r_ok = expected in rld_ans
        if v_ok: vanilla_correct += 1
        if r_ok: rld_correct += 1

        print(f"  Q: {q[:60]}...")
        print(f"    Vanilla:  {'PASS' if v_ok else 'FAIL'} -> {vanilla_ans[:80]}")
        print(f"    RLD:      {'PASS' if r_ok else 'FAIL'} -> {rld_ans[:80]}")
        print(f"    Expected: {expected}")
        print(f"    Genes:    {len(ctx.activated)} active")
        print()

    n = len(questions)
    print("=" * 55)
    print(f"  Vanilla Accuracy:  {vanilla_correct}/{n} = {vanilla_correct/n*100:.1f}%")
    print(f"  RLD Accuracy:      {rld_correct}/{n} = {rld_correct/n*100:.1f}%")
    print("=" * 55)


# ============================================================
async def main():
    rld, precision = await phase1_retrieval()
    await phase2_qwen(rld)
    print("\nBenchmark complete.")


if __name__ == "__main__":
    asyncio.run(main())
