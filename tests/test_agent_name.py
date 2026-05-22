"""Test script to verify agent name changes with persona."""

from personas import get_persona_manager, activate_persona, get_agent_name

def test_agent_name():
    """Test that agent name changes with active persona."""
    manager = get_persona_manager()

    print("=" * 80)
    print("AGENT NAME TEST")
    print("=" * 80)

    # Test default name
    print("\n1. Default (no persona):")
    print(f"   Agent name: {get_agent_name()}")

    # Test Mechanicus
    print("\n2. Activating Mechanicus persona:")
    activate_persona("mechanicus")
    print(f"   Agent name: {get_agent_name()}")

    # Test Cyberpunk
    print("\n3. Activating Cyberpunk persona:")
    activate_persona("cyberpunk")
    print(f"   Agent name: {get_agent_name()}")

    # Test Wizard
    print("\n4. Activating Wizard persona:")
    activate_persona("wizard")
    print(f"   Agent name: {get_agent_name()}")

    # Test deactivate
    print("\n5. Deactivating persona:")
    manager.deactivate_persona()
    print(f"   Agent name: {get_agent_name()}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_agent_name()
