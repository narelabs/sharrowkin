"""Quick memory test - single task to verify memory systems."""

import asyncio
from pathlib import Path
from agent.core import SharrowkinAgent

async def test_memory_quick():
    """Quick test of memory systems."""
    print("=" * 70)
    print("QUICK MEMORY TEST")
    print("=" * 70)

    agent = SharrowkinAgent()
    workspace = Path("C:/Users/danik/Documents/sharrowkin")

    # Task: Create calculator module
    task = """
Создай модуль math_helper.py с функциями:
- add(a, b) - сложение с type hints
- multiply(a, b) - умножение с type hints
- power(a, b) - возведение в степень с type hints

Добавь docstrings для каждой функции.
"""

    print(f"\nTask:\n{task}")
    print("\nExecuting...\n")

    try:
        async for event in agent.run(task, str(workspace)):
            event_type = event.get("type", "unknown")

            if event_type == "phase":
                phase = event.get("phase", "")
                status = event.get("status", "")
                print(f"[PHASE] {phase}: {status}")

            elif event_type == "log":
                level = event.get("level", "info")
                message = event.get("message", "")
                try:
                    # Highlight memory-related messages
                    if any(keyword in message.lower() for keyword in ["memory", "similar", "recall", "dsm", "rld", "trace"]):
                        print(f"[{level.upper()}] *** {message} ***")
                    else:
                        print(f"[{level.upper()}] {message}")
                except UnicodeEncodeError:
                    print(f"[{level.upper()}] <message>")

    except Exception as e:
        print(f"\n[ERROR] {e}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

    # Verify file
    file_path = workspace / "math_helper.py"
    if file_path.exists():
        print(f"\n[OK] math_helper.py created")
        print("\nContent preview:")
        print("-" * 70)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            print(content[:500])
            if len(content) > 500:
                print("...")
    else:
        print(f"\n[FAIL] math_helper.py not found")

if __name__ == "__main__":
    asyncio.run(test_memory_quick())
