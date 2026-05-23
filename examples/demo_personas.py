"""Demo: Persona System with Thematic Agent Customization

This example demonstrates how to use the persona system to customize
the agent's personality, logs, and responses.
"""

from pathlib import Path

from personas import (
    PersonaManager,
    activate_persona,
    deactivate_persona,
    format_log,
    get_persona_manager,
    inject_persona,
)
from personas.llm_integration import LogType


def demo_persona_loading():
    """Demonstrate loading and listing personas."""
    print("=" * 60)
    print("DEMO: Loading Personas")
    print("=" * 60)

    manager = get_persona_manager()
    personas = manager.list_personas()

    print(f"\nFound {len(personas)} personas:")
    for persona in personas:
        print(f"\n  🎭 {persona.name} ({persona.id})")
        print(f"     {persona.description}")
        print(f"     Tags: {', '.join(persona.tags)}")
        print(f"     Colors: {persona.colors.get('primary', 'N/A')}")


def demo_persona_activation():
    """Demonstrate activating personas and formatting logs."""
    print("\n" + "=" * 60)
    print("DEMO: Persona Activation & Log Formatting")
    print("=" * 60)

    personas_to_test = ["mechanicus", "cyberpunk", "wizard"]

    for persona_id in personas_to_test:
        print(f"\n{'─' * 60}")
        print(f"Activating: {persona_id.upper()}")
        print(f"{'─' * 60}")

        if activate_persona(persona_id):
            # Test various log types
            print("\n📋 Sample Logs:")
            print(format_log(LogType.PLAN_START, "analyzing codebase structure"))
            print(format_log(LogType.FILE_READ, "main.py"))
            print(format_log(LogType.FILE_WRITE, "config.json"))
            print(format_log(LogType.TEST_START, "test_authentication.py"))
            print(format_log(LogType.TEST_PASS, "All tests passed!"))
            print(format_log(LogType.SUCCESS, "Feature implementation complete"))
            print(format_log(LogType.ERROR, "line 42: undefined variable"))
        else:
            print(f"❌ Failed to activate persona: {persona_id}")

    # Deactivate
    print(f"\n{'─' * 60}")
    print("Deactivating persona (back to default)")
    print(f"{'─' * 60}")
    deactivate_persona()
    print(format_log(LogType.SUCCESS, "Back to normal mode"))


def demo_prompt_injection():
    """Demonstrate prompt injection with personas."""
    print("\n" + "=" * 60)
    print("DEMO: Prompt Injection")
    print("=" * 60)

    base_prompt = """
You are a helpful coding assistant. Analyze the following code and suggest improvements.

Code:
def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total = total + num
    return total
"""

    print("\n📝 Base Prompt:")
    print(base_prompt[:200] + "...")

    # Test with different personas
    for persona_id in ["mechanicus", "cyberpunk", "wizard"]:
        print(f"\n{'─' * 60}")
        print(f"With {persona_id.upper()} persona:")
        print(f"{'─' * 60}")

        activate_persona(persona_id)
        customized = inject_persona(base_prompt)
        print(customized[:300] + "...")

    deactivate_persona()


def demo_terminology_replacement():
    """Demonstrate terminology replacement."""
    print("\n" + "=" * 60)
    print("DEMO: Terminology Replacement")
    print("=" * 60)

    test_text = """
The code has a bug in the function. We need to fix the error and refactor
the class. After that, we'll run tests and deploy to production.
"""

    print("\n📝 Original Text:")
    print(test_text)

    for persona_id in ["mechanicus", "cyberpunk", "wizard"]:
        print(f"\n{'─' * 60}")
        print(f"With {persona_id.upper()} persona:")
        print(f"{'─' * 60}")

        activate_persona(persona_id)
        manager = get_persona_manager()

        # Apply terminology replacement
        customized = test_text
        if manager.active_persona:
            for standard, themed in manager.active_persona.terminology.items():
                customized = customized.replace(standard, themed)

        print(customized)

    deactivate_persona()


def demo_audio_files():
    """Demonstrate audio file mapping."""
    print("\n" + "=" * 60)
    print("DEMO: Audio File Mapping")
    print("=" * 60)

    manager = get_persona_manager()

    for persona_id in ["mechanicus", "cyberpunk", "wizard"]:
        persona = manager.get_persona(persona_id)
        if persona:
            print(f"\n🎵 {persona.name} Audio Files:")
            for event, audio_file in persona.audio_files.items():
                print(f"  {event}: {audio_file}")


def demo_color_schemes():
    """Demonstrate color schemes for each persona."""
    print("\n" + "=" * 60)
    print("DEMO: Color Schemes")
    print("=" * 60)

    manager = get_persona_manager()

    for persona_id in ["mechanicus", "cyberpunk", "wizard"]:
        persona = manager.get_persona(persona_id)
        if persona:
            print(f"\n🎨 {persona.name} Colors:")
            for color_name, color_value in persona.colors.items():
                print(f"  {color_name}: {color_value}")


def main():
    """Run all persona demos."""
    print("\n🎭 Sharrowkin Persona System Demo")
    print("Thematic Agent Customization")
    print("\n")

    try:
        demo_persona_loading()
    except Exception as e:
        print(f"\n❌ Persona loading demo failed: {e}")

    try:
        demo_persona_activation()
    except Exception as e:
        print(f"\n❌ Persona activation demo failed: {e}")

    try:
        demo_prompt_injection()
    except Exception as e:
        print(f"\n❌ Prompt injection demo failed: {e}")

    try:
        demo_terminology_replacement()
    except Exception as e:
        print(f"\n❌ Terminology replacement demo failed: {e}")

    try:
        demo_audio_files()
    except Exception as e:
        print(f"\n❌ Audio files demo failed: {e}")

    try:
        demo_color_schemes()
    except Exception as e:
        print(f"\n❌ Color schemes demo failed: {e}")

    print("\n" + "=" * 60)
    print("✅ Persona System Demo Complete!")
    print("=" * 60)
    print("\nAvailable Personas:")
    print("  1. Adeptus Mechanicus - Tech-Priest of Mars")
    print("  2. Cyberpunk Netrunner - Rogue AI Hacker")
    print("  3. Arcane Wizard - Master of Code Magic")
    print("\nNext steps:")
    print("  1. Integrate with agent.py for live theming")
    print("  2. Add frontend theme selector UI")
    print("  3. Implement audio playback system")
    print("  4. Create remaining 7 personas")


if __name__ == "__main__":
    main()
