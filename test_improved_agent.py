"""Simple test script for improved agent."""

import asyncio
from pathlib import Path
from agent.core import SharrowkinAgent
from memory.bridge import MemoryBridge

async def test_agent():
    """Test agent with simple task."""
    print("=" * 60)
    print("TESTING IMPROVED AGENT")
    print("=" * 60)

    # Create agent
    agent = SharrowkinAgent()

    # Simple test task
    task = "Создай файл test_hello.py с функцией hello() которая возвращает 'Hello, World!'"
    workspace = Path("C:/Users/danik/Documents/sharrowkin")

    print(f"\nTask: {task}")
    print(f"Workspace: {workspace}")
    print("\nStarting agent...\n")

    # Run agent
    async for event in agent.run(task, str(workspace)):
        event_type = event.get("type", "unknown")

        if event_type == "phase":
            phase = event.get("phase", "")
            status = event.get("status", "")
            print(f"[PHASE] {phase}: {status}")

        elif event_type == "log":
            level = event.get("level", "info")
            message = event.get("message", "")
            print(f"[{level.upper()}] {message}")

        elif event_type == "tool_call":
            tool = event.get("tool", "")
            status = event.get("status", "")
            print(f"[TOOL] {tool}: {status}")

        elif event_type == "cognitive_update":
            mode = event.get("mode", "")
            print(f"[COGNITIVE] Mode: {mode}")

        elif event_type == "content":
            content = event.get("content", "")
            print(f"\n[RESULT]\n{content}\n")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_agent())
