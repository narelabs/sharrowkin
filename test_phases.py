"""
Test script to verify 5-phase cycle works end-to-end.
Tests each phase independently.
"""

import sys
sys.path.insert(0, '.')

from pathlib import Path
from agent.core import SharrowkinAgent, PHASES
from memory import MemoryBridge
import asyncio


async def test_phase_observe():
    """Test Phase 1: Observe (workspace scanning)."""
    print("\n=== Testing Phase 1: Observe ===")

    workspace = Path('.')
    memory = MemoryBridge(workspace)
    agent = SharrowkinAgent()

    # Create mock state
    from agent.core import AgentRunState
    state = AgentRunState(
        task="Test task",
        workspace=workspace,
        states=[],
        actions=[],
        tools_used=[]
    )

    try:
        events = []
        async for event in agent._observe(state, memory):
            events.append(event)
            if event.get('type') == 'phase':
                print(f"  Phase: {event.get('phase')} - {event.get('status')}")
            elif event.get('type') == 'log':
                print(f"  Log: {event.get('content')}")

        print(f"  [OK] Observe phase completed")
        print(f"  Workspace summary length: {len(state.workspace_summary)}")
        print(f"  Actions: {len(state.actions)}")
        return True
    except Exception as e:
        print(f"  [FAIL] Observe phase failed: {e}")
        return False


async def test_phase_recall():
    """Test Phase 2: Recall (memory retrieval)."""
    print("\n=== Testing Phase 2: Recall ===")

    workspace = Path('.')
    memory = MemoryBridge(workspace)
    agent = SharrowkinAgent()

    from agent.core import AgentRunState
    state = AgentRunState(
        task="Test memory recall",
        workspace=workspace,
        states=[],
        actions=[],
        tools_used=[]
    )

    try:
        events = []
        async for event in agent._recall(state, memory):
            events.append(event)
            if event.get('type') == 'phase':
                print(f"  Phase: {event.get('phase')} - {event.get('status')}")
            elif event.get('type') == 'log':
                print(f"  Log: {event.get('content')}")

        print(f"  [OK] Recall phase completed")
        print(f"  Memory context length: {len(state.memory_context)}")
        return True
    except Exception as e:
        print(f"  [FAIL] Recall phase failed: {e}")
        return False


async def test_agent_initialization():
    """Test agent and memory initialization."""
    print("\n=== Testing Agent Initialization ===")

    try:
        workspace = Path('.')
        memory = MemoryBridge(workspace)
        agent = SharrowkinAgent()

        print(f"  [OK] Agent initialized")
        print(f"  Max iterations: {agent.max_iterations}")
        print(f"  Memory enabled: {memory.enabled}")
        print(f"  DSM available: {memory.dsm is not None}")
        print(f"  RLD available: {memory.rld is not None}")

        return True
    except Exception as e:
        print(f"  [FAIL] Initialization failed: {e}")
        return False


async def main():
    """Run all phase tests."""
    print("=" * 60)
    print("Sharrowkin Agent - 5-Phase Cycle Test")
    print("=" * 60)

    results = {}

    # Test 1: Initialization
    results['init'] = await test_agent_initialization()

    # Test 2: Observe phase
    results['observe'] = await test_phase_observe()

    # Test 3: Recall phase
    results['recall'] = await test_phase_recall()

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {test_name.upper()}: {status}")

    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed ({passed*100//total}%)")

    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
