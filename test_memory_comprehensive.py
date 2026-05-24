"""Comprehensive memory systems test for Sharrowkin agent."""

import asyncio
from pathlib import Path
from agent.core import SharrowkinAgent

async def test_memory_systems():
    """Test all 4 memory systems with sequential tasks."""
    print("=" * 70)
    print("COMPREHENSIVE MEMORY SYSTEMS TEST")
    print("=" * 70)

    agent = SharrowkinAgent()
    workspace = Path("C:/Users/danik/Documents/sharrowkin")

    # Test 1: First task - Create calculator module
    print("\n" + "=" * 70)
    print("TEST 1: Create calculator module (DSM + RLD learning)")
    print("=" * 70)

    task1 = """
Создай модуль calculator.py с функциями:
- add(a, b) - сложение
- subtract(a, b) - вычитание
- multiply(a, b) - умножение
- divide(a, b) - деление (с проверкой на 0)

Добавь docstrings и type hints.
"""

    print(f"\nTask 1:\n{task1}")
    print("\nExecuting...\n")

    try:
        async for event in agent.run(task1, str(workspace)):
            event_type = event.get("type", "unknown")
            if event_type == "phase":
                phase = event.get("phase", "")
                status = event.get("status", "")
                print(f"[PHASE] {phase}: {status}")
            elif event_type == "log":
                level = event.get("level", "info")
                message = event.get("message", "")
                try:
                    print(f"[{level.upper()}] {message}")
                except UnicodeEncodeError:
                    print(f"[{level.upper()}] <message>")
    except Exception as e:
        print(f"[ERROR] {e}")

    print("\n" + "=" * 70)
    print("Waiting 3 seconds for memory to persist...")
    print("=" * 70)
    await asyncio.sleep(3)

    # Test 2: Similar task - Should use memory from Test 1
    print("\n" + "=" * 70)
    print("TEST 2: Create string_utils module (should recall calculator pattern)")
    print("=" * 70)

    task2 = """
Создай модуль string_utils.py с функциями:
- uppercase(s) - в верхний регистр
- lowercase(s) - в нижний регистр
- reverse(s) - реверс строки
- count_words(s) - подсчет слов

Используй тот же стиль что и в других модулях проекта.
"""

    print(f"\nTask 2:\n{task2}")
    print("\nExecuting...\n")

    try:
        async for event in agent.run(task2, str(workspace)):
            event_type = event.get("type", "unknown")
            if event_type == "phase":
                phase = event.get("phase", "")
                status = event.get("status", "")
                print(f"[PHASE] {phase}: {status}")
            elif event_type == "log":
                level = event.get("level", "info")
                message = event.get("message", "")
                try:
                    if "memory" in message.lower() or "similar" in message.lower():
                        print(f"[{level.upper()}] >>> {message} <<<")  # Highlight memory usage
                    else:
                        print(f"[{level.upper()}] {message}")
                except UnicodeEncodeError:
                    print(f"[{level.upper()}] <message>")
    except Exception as e:
        print(f"[ERROR] {e}")

    print("\n" + "=" * 70)
    print("Waiting 3 seconds for memory to persist...")
    print("=" * 70)
    await asyncio.sleep(3)

    # Test 3: Error correction - Should learn from failure
    print("\n" + "=" * 70)
    print("TEST 3: Create validator with intentional complexity (self-correction test)")
    print("=" * 70)

    task3 = """
Создай модуль validator.py с функциями:
- validate_email(email) - проверка email (должен содержать @ и .)
- validate_phone(phone) - проверка телефона (10 цифр)
- validate_age(age) - проверка возраста (18-120)

Каждая функция должна возвращать tuple (bool, str) где bool - результат, str - сообщение об ошибке.
Добавь тесты в tests/test_validator.py.
"""

    print(f"\nTask 3:\n{task3}")
    print("\nExecuting...\n")

    try:
        async for event in agent.run(task3, str(workspace)):
            event_type = event.get("type", "unknown")
            if event_type == "phase":
                phase = event.get("phase", "")
                status = event.get("status", "")
                print(f"[PHASE] {phase}: {status}")
            elif event_type == "log":
                level = event.get("level", "info")
                message = event.get("message", "")
                try:
                    if "memory" in message.lower() or "similar" in message.lower() or "retry" in message.lower():
                        print(f"[{level.upper()}] >>> {message} <<<")
                    else:
                        print(f"[{level.upper()}] {message}")
                except UnicodeEncodeError:
                    print(f"[{level.upper()}] <message>")
    except Exception as e:
        print(f"[ERROR] {e}")

    print("\n" + "=" * 70)
    print("Waiting 3 seconds for memory to persist...")
    print("=" * 70)
    await asyncio.sleep(3)

    # Test 4: Recall previous work - Should use all memory systems
    print("\n" + "=" * 70)
    print("TEST 4: Create utils package combining previous modules (full memory test)")
    print("=" * 70)

    task4 = """
Создай файл utils/__init__.py который импортирует и экспортирует все функции из:
- calculator.py
- string_utils.py
- validator.py

Используй паттерны и стиль из предыдущих модулей.
"""

    print(f"\nTask 4:\n{task4}")
    print("\nExecuting...\n")

    try:
        async for event in agent.run(task4, str(workspace)):
            event_type = event.get("type", "unknown")
            if event_type == "phase":
                phase = event.get("phase", "")
                status = event.get("status", "")
                print(f"[PHASE] {phase}: {status}")
            elif event_type == "log":
                level = event.get("level", "info")
                message = event.get("message", "")
                try:
                    if "memory" in message.lower() or "similar" in message.lower():
                        print(f"[{level.upper()}] >>> {message} <<<")
                    else:
                        print(f"[{level.upper()}] {message}")
                except UnicodeEncodeError:
                    print(f"[{level.upper()}] <message>")
    except Exception as e:
        print(f"[ERROR] {e}")

    print("\n" + "=" * 70)
    print("MEMORY TEST COMPLETE")
    print("=" * 70)

    # Verify created files
    print("\n" + "=" * 70)
    print("VERIFICATION - Checking created files:")
    print("=" * 70)

    files_to_check = [
        "calculator.py",
        "string_utils.py",
        "validator.py",
        "tests/test_validator.py",
        "utils/__init__.py"
    ]

    for file in files_to_check:
        file_path = workspace / file
        if file_path.exists():
            print(f"  [OK] {file} - EXISTS")
        else:
            print(f"  [MISSING] {file} - NOT FOUND")

if __name__ == "__main__":
    asyncio.run(test_memory_systems())
