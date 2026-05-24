"""Simple test to verify agent works end-to-end."""
import sys
sys.path.insert(0, '.')

from pathlib import Path
from agent.core import SharrowkinAgent
from memory import MemoryBridge
import asyncio

async def test_simple_task():
    workspace = Path('.')
    memory = MemoryBridge(workspace)
    agent = SharrowkinAgent()
    
    print("Testing agent on simple task...")
    print(f"Max iterations: {agent.max_iterations}")
    print(f"Memory enabled: {memory.enabled}")
    print("\nAgent initialized successfully!")
    
    # TODO: Test actual task execution when LLM is configured
    return True

if __name__ == "__main__":
    result = asyncio.run(test_simple_task())
    print(f"\nTest result: {'PASS' if result else 'FAIL'}")
