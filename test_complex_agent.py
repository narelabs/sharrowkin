"""Complex test for agent - REST API endpoint with validation and tests."""

import asyncio
from pathlib import Path
from agent.core import SharrowkinAgent

async def test_complex_task():
    """Test agent with complex multi-file task."""
    print("=" * 60)
    print("COMPLEX AGENT TEST - REST API ENDPOINT")
    print("=" * 60)

    agent = SharrowkinAgent()

    # Complex task: Create REST API endpoint with validation and tests
    task = """
Создай REST API endpoint для управления пользователями:

1. Файл api/routes/users.py:
   - POST /users - создать пользователя
   - GET /users/{id} - получить пользователя
   - Валидация: email должен быть валидным, age >= 18
   - Используй FastAPI и Pydantic

2. Файл api/models/user.py:
   - Pydantic модель User с полями: id, name, email, age
   - Валидаторы для email и age

3. Файл tests/test_users_api.py:
   - Тесты для обоих endpoints
   - Тест валидации (невалидный email, age < 18)
   - Используй pytest и httpx

Все файлы должны быть связаны и работать вместе.
"""

    workspace = Path("C:/Users/danik/Documents/sharrowkin")

    print(f"\nTask:\n{task}")
    print(f"\nWorkspace: {workspace}")
    print("\nStarting agent...\n")

    # Run agent
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
                # Skip unicode characters that cause issues
                try:
                    print(f"[{level.upper()}] {message}")
                except UnicodeEncodeError:
                    print(f"[{level.upper()}] <message with unicode>")

            elif event_type == "tool_call":
                tool = event.get("tool", "")
                status = event.get("status", "")
                print(f"[TOOL] {tool}: {status}")

            elif event_type == "cognitive_update":
                mode = event.get("mode", "")
                print(f"[COGNITIVE] {mode}")

            elif event_type == "content":
                content = event.get("content", "")
                try:
                    print(f"\n[RESULT]\n{content}\n")
                except UnicodeEncodeError:
                    print(f"\n[RESULT]\n<content with unicode>\n")

    except Exception as e:
        print(f"\n[ERROR] {e}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_complex_task())
