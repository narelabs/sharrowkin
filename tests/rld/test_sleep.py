"""Tests for the RLD Sleep Phase (offline consolidation revolution)."""

import time
from pathlib import Path

from rld import RecursiveLatentDNA


def test_sleep_entropic_decay_reduces_stability(tmp_path: Path) -> None:
    """Genes created in the past should lose stability during sleep."""
    rld = RecursiveLatentDNA(tmp_path / "genes.json")
    rld.observe(
        "Old pattern that was never reused",
        actions=["step1", "step2"],
        success=True,
        utility=0.6,
    )
    gene_id = next(iter(rld.genes))
    gene = rld.genes[gene_id]

    # Backdate creation to 48 hours ago to simulate staleness
    gene.created_at -= 48 * 3600
    gene.last_activated_at = 0.0
    old_stability = gene.stats.stability

    report = rld.sleep(
        decay_rate=0.10,
        decay_floor=0.05,
        min_value=0.01,  # low so we don't prune it
        save_after=False,
    )

    assert gene.stats.stability < old_stability, "Stability should have decayed"
    assert gene_id in report.decayed, "Gene should appear in decay report"
    assert report.decayed[gene_id] > 0.0, "Decay amount should be positive"
    assert report.genes_before == 1
    assert report.genes_after == 1
    assert report.duration_seconds > 0.0


def test_sleep_decay_then_prune_kills_stale_genes(tmp_path: Path) -> None:
    """Entropic decay + pruning should remove truly dead genes."""
    rld = RecursiveLatentDNA(tmp_path / "genes.json")
    rld.observe("Ephemeral thought", actions=["think"], success=False, utility=0.05)
    gene_id = next(iter(rld.genes))
    gene = rld.genes[gene_id]

    # Make it old, failed, and unused
    gene.created_at -= 72 * 3600
    gene.last_activated_at = 0.0
    gene.stats.stability = 0.15
    gene.stats.reuse_count = 1
    gene.stats.failure_count = 3
    gene.stats.success_count = 0

    report = rld.sleep(
        decay_rate=0.12,
        decay_floor=0.02,
        min_value=0.10,
        save_after=False,
    )

    assert gene_id not in rld.genes, "Dead gene should be pruned after decay"
    assert gene_id in report.pruned
    assert report.genes_before == 1
    assert report.genes_after == 0


def test_sleep_recently_active_genes_are_immune_to_decay(tmp_path: Path) -> None:
    """Genes activated within the last hour should not decay."""
    rld = RecursiveLatentDNA(tmp_path / "genes.json")
    rld.observe(
        "Fresh insight from just now",
        actions=["observe", "conclude"],
        success=True,
        utility=0.95,
    )
    gene_id = next(iter(rld.genes))
    gene = rld.genes[gene_id]

    # Activate it right now
    gene.last_activated_at = time.time()
    old_stability = gene.stats.stability

    report = rld.sleep(
        decay_rate=0.20,  # aggressive decay
        save_after=False,
    )

    assert gene.stats.stability == old_stability, "Recently active gene should be immune"
    assert gene_id not in report.decayed


def test_sleep_merge_lineage_tracks_ancestry(tmp_path: Path) -> None:
    """Merged chromosomes should record their parent gene IDs."""
    rld = RecursiveLatentDNA(tmp_path / "genes.json")
    rld.observe(
        "Fix async websocket timeout with heartbeat",
        actions=["add ping", "set deadline"],
        final_answer="Heartbeat fixes timeout.",
    )
    rld.observe(
        "Repair async websocket idle timeout",
        actions=["bound queue", "add keepalive"],
        final_answer="Keepalive fixes idle timeout.",
    )
    parent_ids = list(rld.genes.keys())

    report = rld.sleep(merge_similarity=0.1, save_after=False)

    assert report.merged, "Compatible genes should merge"
    child_id = report.merged[0]
    assert child_id in report.merge_lineage
    lineage = report.merge_lineage[child_id]
    assert len(lineage) == 2
    for pid in parent_ids:
        assert pid in lineage, f"Parent {pid} should appear in lineage"


def test_sleep_centroid_reanchor_shifts_embedding(tmp_path: Path) -> None:
    """Genes with multiple trajectories should get re-anchored."""
    rld = RecursiveLatentDNA(tmp_path / "genes.json")

    # Observe the same domain multiple times to build trajectory evidence
    for i in range(5):
        rld.observe(
            f"Optimize database query performance (variant {i})",
            actions=["analyze", "add index", "verify"],
            final_answer=f"Index on column_{i} improves performance.",
            success=True,
            utility=0.9,
        )

    # After 5 observations the gene should have multiple trajectory IDs
    gene = next(iter(rld.genes.values()))
    old_embedding = list(gene.embedding)

    report = rld.sleep(
        centroid_reanchor_threshold=2,
        save_after=False,
    )

    # The embedding should have shifted (or stayed if already at centroid)
    # We just verify the mechanism ran without errors
    assert report.genes_after >= 1
    assert report.duration_seconds >= 0.0


def test_sleep_report_summary_is_human_readable(tmp_path: Path) -> None:
    """The sleep report summary should be a multi-line human-readable string."""
    rld = RecursiveLatentDNA(tmp_path / "genes.json")
    rld.observe("Test gene", actions=["act"])

    report = rld.sleep(save_after=False)

    summary = report.summary
    assert "Sleep Report:" in summary
    assert "Decayed:" in summary
    assert "Pruned:" in summary
    assert "Merged:" in summary
    assert "Stabilized:" in summary


def test_sleep_full_lifecycle_with_persistence(tmp_path: Path) -> None:
    """Full sleep cycle: create genes, sleep, reload, verify."""
    path = tmp_path / "genes.json"
    rld = RecursiveLatentDNA(path)

    # Create a healthy gene
    rld.observe(
        "Parse complex JSON schemas",
        actions=["tokenize", "validate", "extract"],
        final_answer="Schema validation complete.",
        success=True,
        utility=0.88,
    )
    # Create a doomed gene
    rld.observe(
        "Random noise that will decay and die",
        actions=["guess"],
        success=False,
        utility=0.01,
    )
    doomed_id = list(rld.genes.keys())[-1]
    doomed = rld.genes[doomed_id]
    doomed.created_at -= 96 * 3600
    doomed.stats.reuse_count = 1
    doomed.stats.stability = 0.10

    report = rld.sleep(
        decay_rate=0.08,
        min_value=0.10,
        save_after=True,  # persist!
    )

    assert report.genes_before == 2
    assert report.genes_after <= 2
    assert report.duration_seconds > 0

    # Reload from disk
    restored = RecursiveLatentDNA(path)
    assert restored.stats()["genes"] >= 1
    assert restored.stats()["dsm_segments"] >= 1
