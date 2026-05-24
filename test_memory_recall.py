"""Test memory recall - second similar task."""

import asyncio
from pathlib import Path
from agent.core import SharrowkinAgent

async def test_memory_recall():
    """Test if agent recalls previous similar task."""
    print("=" * 70)
    print("MEMORY RECALL TEST - Similar task to math_helper.py")
    print("=" * 70)

    agent = SharrowkinAgent()
    workspace = Path("C:/Users/danik/Documents/sharrowkin")

    # Similar task - should recall math_helper.py pattern
    task = """
Создай модуль string_ops.py с функциями:
- concat(s1, s2) - конкатенация строк с type hints
- repeat(s, n) - повторение строки n раз с type hints
- reverse(s) - реверс строки с type hints

Используй тот же стиль docstrings что и в других модулях проекта.
"""

    print(f"\nTask:\n{task}")
    print("\nExpected: Agent should recall math_helper.py pattern")
    print("\nExecuting...\n")

    memory_found = False
    similar_count = 0

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
                    # Check for memory usage
                    if "similar" in message.lower() and "solution" in message.lower():
                        memory_found = True
                        # Extract count if present
                        import re
                        match = re.search(r'(\d+)\s+similar', message)
                        if match:
                            similar_count = int(match.group(1))
                        print(f"[{level.upper()}] *** MEMORY FOUND: {message} ***")
                    elif any(keyword in message.lower() for keyword in ["memory", "recall", "dsm", "rld", "trace"]):
                        print(f"[{level.upper()}] *** {message} ***")
                    else:
                        print(f"[{level.upper()}] {message}")
                except UnicodeEncodeError:
                    print(f"[{level.upper()}] <message>")

    except Exception as e:
        print(f"\n[ERROR] {e}")

    print("\n" + "=" * 70)
    print("MEMORY RECALL TEST RESULTS")
    print("=" * 70)

    if memory_found:
        print(f"[SUCCESS] Memory system WORKING - Found {similar_count} similar solutions")
    else:
        print(f"[WARNING] Memory system NOT USED - No similar solutions found")

    # Verify file
    file_path = workspace / "string_ops.py"
    if file_path.exists():
        print(f"[OK] string_ops.py created")

        # Check if style matches math_helper.py
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for similar patterns
        has_type_hints = "def " in content and "->" in content
        has_docstrings = '"""' in content
        has_args_section = "Args:" in content
        has_returns_section = "Returns:" in content
        has_examples = "Examples:" in content

        print("\nStyle consistency check:")
        print(f"  Type hints: {'YES' if has_type_hints else 'NO'}")
        print(f"  Docstrings: {'YES' if has_docstrings else 'NO'}")
        print(f"  Args section: {'YES' if has_args_section else 'NO'}")
        print(f"  Returns section: {'YES' if has_returns_section else 'NO'}")
        print(f"  Examples section: {'YES' if has_examples else 'NO'}")

        if all([has_type_hints, has_docstrings, has_args_section, has_returns_section]):
            print("\n[SUCCESS] Style matches math_helper.py pattern!")
        else:
            print("\n[WARNING] Style differs from math_helper.py")

        print("\nContent preview:")
        print("-" * 70)
        print(content[:600])
        if len(content) > 600:
            print("...")
    else:
        print(f"[FAIL] string_ops.py not found")

if __name__ == "__main__":
    asyncio.run(test_memory_recall())
