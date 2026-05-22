"""Quick test for classify_intent heuristic."""
import sys
sys.path.insert(0, "backend")
from core.llm_client import GeminiClient

g = GeminiClient()
tests = ["привет", "Привет", "hello", "кто ты", "изучай проект", "fix the bug"]
for t in tests:
    result = g.classify_intent(t)
    tag = "CONV" if result.get("is_conversational") else "TASK"
    print(f"  [{tag}] '{t}' => {result}")
