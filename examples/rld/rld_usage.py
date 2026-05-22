from rld import RecursiveLatentDNA


def main() -> None:
    rld = RecursiveLatentDNA(".rld/example_genes.json")
    rld.observe(
        "Fix a websocket timeout in an async Rust service",
        states=[
            "Bug report mentions dropped websocket connections.",
            "Root cause is missing ping deadline and unbounded producer queue.",
            "Patch adds ping/pong deadline and bounded channel backpressure.",
        ],
        actions=[
            "Locate websocket loop.",
            "Identify missing heartbeat and queue bounds.",
            "Add cancellation-safe cleanup and tests.",
        ],
        final_answer="Use ping deadlines, bounded channels and cancellation-safe task cleanup.",
        tools_used=["ripgrep", "pytest"],
        utility=0.92,
    )
    context = rld.active_context("How should I repair another Rust websocket timeout?", top_k=3)
    print(context.context_text)
    print(rld.consolidate().to_dict())
    rld.save()


if __name__ == "__main__":
    main()
