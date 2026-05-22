"""Test script to verify deep persona immersion is working."""

from personas import get_persona_manager, activate_persona, inject_persona

def test_persona_immersion():
    """Test that personas inject deep character immersion."""
    manager = get_persona_manager()

    print("=" * 80)
    print("PERSONA IMMERSION TEST")
    print("=" * 80)

    # List all loaded personas
    personas = manager.list_personas()
    print(f"\nLoaded {len(personas)} personas:")
    for p in personas:
        print(f"  - {p.id}: {p.name}")

    # Test Mechanicus persona
    print("\n" + "=" * 80)
    print("TEST 1: ADEPTUS MECHANICUS")
    print("=" * 80)

    activate_persona("mechanicus")

    base_prompt = "You are Sharrowkin, a friendly AI coding assistant."
    injected = inject_persona(base_prompt)

    print("\nBase prompt:")
    print(base_prompt)

    print("\nInjected prompt (first 500 chars):")
    print(injected[:500])
    print("...")

    # Check for key immersion phrases
    immersion_checks = [
        ("Magos Digitalis", "[OK] Character name present"),
        ("Tech-Priest", "[OK] Role present"),
        ("Omnissiah", "[OK] Religious terminology present"),
        ("centuries", "[OK] Backstory depth present"),
        ("you ARE a Tech-Priest", "[OK] Deep immersion statement present"),
        ("Machine Spirit", "[OK] Lore terminology present"),
    ]

    print("\nImmersion depth checks:")
    for phrase, success_msg in immersion_checks:
        if phrase in injected:
            print(f"  {success_msg}")
        else:
            print(f"  [FAIL] Missing: {phrase}")

    # Test Cyberpunk persona
    print("\n" + "=" * 80)
    print("TEST 2: CYBERPUNK NETRUNNER")
    print("=" * 80)

    activate_persona("cyberpunk")
    injected = inject_persona(base_prompt)

    print("\n🔮 Injected prompt (first 500 chars):")
    print(injected[:500])
    print("...")

    immersion_checks = [
        ("V-TECH", "✅ Character name present"),
        ("Arasaka", "✅ Lore reference present"),
        ("2077", "✅ Timeline present"),
        ("you ARE one", "✅ Deep immersion statement present"),
        ("the Net", "✅ World terminology present"),
    ]

    print("\n🔍 Immersion depth checks:")
    for phrase, success_msg in immersion_checks:
        if phrase in injected:
            print(f"  {success_msg}")
        else:
            print(f"  ❌ Missing: {phrase}")

    # Test Wizard persona
    print("\n" + "=" * 80)
    print("TEST 3: ARCANE WIZARD")
    print("=" * 80)

    activate_persona("wizard")
    injected = inject_persona(base_prompt)

    print("\n🔮 Injected prompt (first 500 chars):")
    print(injected[:500])
    print("...")

    immersion_checks = [
        ("Archmage Codexus", "✅ Character name present"),
        ("three centuries", "✅ Backstory depth present"),
        ("Tower of Abstraction", "✅ Lore location present"),
        ("you ARE an Archmage", "✅ Deep immersion statement present"),
        ("Magic is real", "✅ Reality statement present"),
    ]

    print("\n🔍 Immersion depth checks:")
    for phrase, success_msg in immersion_checks:
        if phrase in injected:
            print(f"  {success_msg}")
        else:
            print(f"  ❌ Missing: {phrase}")

    print("\n" + "=" * 80)
    print("PERSONA IMMERSION TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_persona_immersion()
