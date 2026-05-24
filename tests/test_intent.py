import asyncio
import sys
from pathlib import Path
from core.llm.client import GeminiClient

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_intent_detection():
    """Test intent detection with Gemini."""
    client = GeminiClient()
    
    # Test coding intent
    response = client.generate(
        "Write a Python function to calculate fibonacci numbers"
    )
    assert response is not None
    assert len(response) > 0
    
    # Test question intent
    response = client.generate(
        "What is the capital of France?"
    )
    assert response is not None
    assert len(response) > 0


if __name__ == "__main__":
    test_intent_detection()
    print("✓ Intent detection tests passed")
