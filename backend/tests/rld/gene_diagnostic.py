"""
RLD Gene Diagnostic Tool (Fixed)
Lists and describes all synthesized reasoning genes in the current library.
"""
import sys, os, json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from rld.core import RecursiveLatentDNA

def main():
    path = ".rld_gsm8k_knowledge.json"
    if not os.path.exists(path):
        print("Knowledge file not found.")
        return

    rld = RecursiveLatentDNA(storage_path=path)
    print("=" * 80)
    print(f"  RLD GENE LIBRARY DIAGNOSTIC - Total Genes: {len(rld.genes)}")
    print("=" * 80)

    for i, gene in enumerate(rld.genes.values()):
        # Use task_context as the primary description
        ctx = gene.task_context
        # Get the first reasoning step if available
        step = gene.reasoning_steps[0] if gene.reasoning_steps else "No specific steps"
        
        desc = f"CTX: {ctx} | STEP: {step}"
        display_text = (desc[:100] + '...') if len(desc) > 100 else desc
        
        print(f"[{i+1:03d}] ID: {gene.id[:8]} | {display_text}")

    print("=" * 80)

if __name__ == "__main__":
    main()
