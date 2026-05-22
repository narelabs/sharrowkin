import json
from pathlib import Path

from rld import GENE_SCHEMA, RecursiveLatentDNA


def test_observe_generates_reasoning_gene_and_activates_it(tmp_path: Path) -> None:
    rld = RecursiveLatentDNA(tmp_path / "genes.json", activation_threshold=0.2, top_k=2)

    trajectory = rld.observe(
        "Debug Rust websocket timeout",
        states=[
            "Connections close after idle period.",
            "Missing ping/pong deadline causes stale sockets.",
        ],
        actions=[
            "Find websocket event loop.",
            "Add bounded channel and heartbeat deadline.",
            "Validate cancellation-safe cleanup.",
        ],
        final_answer="Bounded channels plus ping deadlines solve the timeout.",
        tools_used=["rg", "pytest"],
        utility=0.95,
    )
    context = rld.active_context("Fix another websocket timeout in Rust")

    assert trajectory.id in next(iter(rld.genes.values())).source_trajectory_ids
    assert len(context.activated) == 1
    assert "RLD GENE" in context.context_text
    assert "latent_delta=trajectory_delta" in context.context_text
    assert "bounded channel" in context.context_text.lower()
    gene = next(iter(rld.genes.values()))
    assert gene.latent_states
    assert gene.latent_delta is not None
    assert rld.stats()["dsm_backend"] is True
    assert rld.stats()["indexed_genes"] == 1
    assert rld.stats()["dsm_segments"] == 1
    assert context.traces[0].gene_id == gene.id
    assert context.traces[0].dsm_segment_id


def test_persistence_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "genes.json"
    rld = RecursiveLatentDNA(path)
    rld.observe("Summarize a long research note", actions=["Extract claims", "Build outline"])
    rld.save()

    restored = RecursiveLatentDNA(path)

    assert restored.stats()["genes"] == 1
    assert restored.stats()["indexed_genes"] == 1
    assert restored.active_context("research outline", threshold=0.0).gene_ids
    assert restored.stats()["gene_schema"]["required"] == GENE_SCHEMA["required"]


def test_consolidation_prunes_failed_gene(tmp_path: Path) -> None:
    rld = RecursiveLatentDNA(tmp_path / "genes.json")
    gene = rld.observe(
        "Bad reasoning pattern",
        actions=["Guess without evidence"],
        success=False,
        utility=0.0,
    )
    gene_id = next(iter(rld.genes))
    rld.record_outcome(gene_id, success=False, utility=0.0)

    report = rld.consolidate(min_value=0.5)

    assert gene.id in rld.trajectories
    assert gene_id in report.pruned
    assert gene_id not in rld.genes


def test_consolidation_merges_compatible_genes(tmp_path: Path) -> None:
    rld = RecursiveLatentDNA(tmp_path / "genes.json")
    rld.observe(
        "Repair async websocket timeout",
        actions=["Bound queue", "Set ping deadline", "Check cleanup"],
        final_answer="Bounded queues and ping deadline fix idle timeout.",
        metadata={"variant": "second"},
    )
    rld.observe(
        "Fix websocket timeout in async service",
        actions=["Inspect async loop", "Add heartbeat", "Run tests"],
        final_answer="Heartbeat fixes idle timeout.",
    )

    report = rld.consolidate(merge_similarity=0.1)

    assert report.merged
    assert rld.stats()["genes"] == 1
    assert rld.stats()["dsm_segments"] == 1
    merged = next(iter(rld.genes.values()))
    assert merged.parent_gene_ids
    assert merged.latent_delta is not None


def test_record_outcome_stabilizes_reused_gene(tmp_path: Path) -> None:
    rld = RecursiveLatentDNA(tmp_path / "genes.json")
    rld.observe("Solve arithmetic by decomposing expression", actions=["Parse", "Evaluate"])
    gene_id = next(iter(rld.genes))

    for _ in range(3):
        rld.active_context("arithmetic expression parse evaluate", threshold=0.0)
        rld.record_outcome(gene_id, success=True, utility=0.9)

    report = rld.consolidate(stabilize_reuse=3)

    assert gene_id in report.stabilized
    assert rld.genes[gene_id].stats.stability > 0.5


def test_mcp_exposes_rld_gene_tools(tmp_path: Path) -> None:
    from dsm import DynamicSegmentedMemory
    from dsm.mcp_server import DsmMcpServer

    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    server = DsmMcpServer(memory)

    observed = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "rld_observe",
                "arguments": {
                    "task": "Fix websocket timeout",
                    "actions": ["Add heartbeat"],
                    "final_answer": "Use ping deadlines.",
                },
            },
        }
    )
    activated = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "rld_activate",
                "arguments": {"query": "websocket timeout", "threshold": 0.0},
            },
        }
    )

    assert observed is not None
    assert activated is not None
    observed_payload = json.loads(observed["result"]["content"][0]["text"])
    activated_payload = json.loads(activated["result"]["content"][0]["text"])
    assert observed_payload["trajectory_id"]
    assert activated_payload["gene_ids"]


def test_formal_policy_and_schema_are_exposed(tmp_path: Path) -> None:
    from rld import HashLatentEncoder, WeightedDSMPolicy

    policy = WeightedDSMPolicy(threshold=0.0, top_k=1, dense_weight=1.0, trigger_weight=0.0)
    rld = RecursiveLatentDNA(
        tmp_path / "genes.json",
        latent_encoder=HashLatentEncoder(),
        dsm_policy=policy,
    )
    rld.observe(
        "Transform an observed failure into a reusable repair plan",
        states=["Failure observed", "Patch verified"],
        actions=["Extract invariant", "Apply repair"],
        final_answer="Reuse invariant repair plan.",
    )

    context = rld.active_context("verified repair plan")

    assert len(context.activated) == 1
    assert context.traces[0].probability >= 0.0
    assert rld.stats()["gene_schema"]["properties"]["latent_delta"]
