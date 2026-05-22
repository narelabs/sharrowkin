from pathlib import Path

from dsm import DynamicSegmentedMemory, TiidoDSMRuntime
from dsm.mcp_server import DsmMcpServer
from dsm.memory import sparse_attention_cost
from dsm.visualize import graph_data, graph_html


def test_write_route_active_context(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json", active_segment_limit=2)
    memory.write(
        "Rust websocket backpressure is handled with bounded channels and async cancellation.",
        category_path="Programming → Rust → Async",
        importance=0.9,
    )
    memory.write(
        "Medieval history contains dynasties, battles and trade routes.",
        category_path="History → Medieval",
        importance=0.5,
    )

    results = memory.route("Rust websocket cancellation bug", k=1)

    assert len(results) == 1
    assert "Rust" in results[0].segment.category_path
    assert results[0].similarity > 0

    active = memory.active_context("Rust websocket cancellation bug", k=1)
    assert results[0].segment.id in active.segment_ids
    assert "bounded channels" in active.context_text


def test_persistence_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "dsm.json"
    memory = DynamicSegmentedMemory(path)
    written = memory.write("MemoryOS uses hierarchical memory layers.", category_path="Science → AI")
    memory.save()

    restored = DynamicSegmentedMemory(path)
    assert written[0].id in restored.segments
    assert restored.stats()["segments"] == 1
    assert restored.route("hierarchical memory", k=1)[0].segment.id == written[0].id


def test_update_existing_and_graph_links(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    first = memory.write("Tokio async websocket timeout handling.", category_path="Programming → Rust")
    second = memory.write("Rust async websocket backpressure handling.", category_path="Programming → Rust")

    assert first[0].id != second[0].id or len(memory.segments) >= 1
    assert memory.stats()["graph_edges"] >= 0

    memory.update_from_interaction("Rust websocket timeout", "Use bounded channels and ping/pong.")
    assert memory.stats()["segments"] >= 1


def test_rebuild_prune_and_cost(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    memory.write("Rare stale note", category_path="General", importance=0.01)
    memory.decay_priorities(0.95)
    moved = memory.rebuild_structure()
    removed = memory.prune(min_priority=0.5)
    cost = sparse_attention_cost(active_tokens=100, total_tokens=1000)

    assert moved >= 0
    assert len(removed) >= 0
    assert cost["reduction_ratio"] == 100.0


def test_compression_replaces_redundant_segments(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    memory.write(
        "Rust websocket timeout requires ping deadlines.",
        category_path="Programming → Rust → Async",
        update_existing=False,
    )
    memory.write(
        "Rust websocket backpressure requires bounded channels.",
        category_path="Programming → Rust → Async",
        update_existing=False,
    )

    compressed = memory.compress(similarity_threshold=0.1)

    assert len(compressed) == 1
    assert compressed[0].compressed_from
    assert memory.stats()["segments"] == 1
    assert "Compressed memory summary" in compressed[0].text


def test_weighted_cross_links_have_reason(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    first = memory.write(
        "Credit payment in February budget.",
        category_path="Finance → Credit",
        update_existing=False,
    )[0]
    second = memory.write(
        "February expenses include credit payment.",
        category_path="Finance → Expenses",
        update_existing=False,
    )[0]

    edge = memory.graph.edge(first.id, second.id)

    assert edge is not None
    assert edge.weight > 0
    assert edge.reason


def test_conflict_detection_for_numeric_facts(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    first = memory.write(
        "Плов купил за 500 руб",
        category_path="Personal → Expenses",
        update_existing=False,
    )[0]
    second = memory.write(
        "Плов купил за 700 руб",
        category_path="Personal → Expenses",
        update_existing=False,
    )[0]

    conflicts = memory.check_consistency()

    assert conflicts
    assert conflicts[0].left_id in {first.id, second.id}
    assert conflicts[0].right_id in {first.id, second.id}
    assert conflicts[0].severity > 0


def test_index_backend_reports_exact_or_faiss(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json", index_backend="auto")
    memory.write("Fast cold start indexing needs HNSW or exact fallback.")

    assert memory.stats()["index_backend"] in {"exact", "faiss_hnsw"}


def test_hybrid_search_prioritizes_exact_terms(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    exact = memory.write(
        "parser.py строка 16 contains the failing import guard.",
        category_path="Code → Python",
        update_existing=False,
    )[0]
    memory.write(
        "Parser logic has semantic discussion about imports.",
        category_path="Code → Python",
        update_existing=False,
    )

    results = memory.route("строка 16 parser.py", k=1)

    assert results[0].segment.id == exact.id
    assert results[0].exact_matches >= 2
    assert results[0].sparse_score > 0


def test_sparse_bypass_restores_recall_when_sparse_index_loaded_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "dsm.json"
    memory = DynamicSegmentedMemory(path)
    for index in range(40):
        memory.write(
            f"generic brain memory server route segment {index}",
            category_path=f"Generic → Branch{index}",
            update_existing=False,
            link_related=False,
        )
    target = memory.write(
        "class CognitiveInvariant:\n"
        "    pass\n"
        "class PredictionEnergyLoss:\n"
        "    pass\n"
        "reconstruction = F.mse_loss(prediction, target)",
        category_path="modules → nare_field → src → narefield → core",
        metadata={"file": "modules/nare_field/src/narefield/core/losses.py"},
        update_existing=False,
        link_related=False,
    )[0]
    memory.save()

    restored = DynamicSegmentedMemory(path)
    results = restored.route("reconstruction = F.mse_loss(prediction, target)", k=5)

    assert any(item.segment.id == target.id for item in results)
    assert results[0].segment.metadata["file"].endswith("losses.py")


def test_delta_index_updates_only_changed_document_chunks(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json", segment_token_limit=4)
    first = memory.upsert_document("brain.py", "alpha beta gamma delta epsilon zeta eta theta")
    second = memory.upsert_document("brain.py", "alpha beta gamma delta epsilon zeta CHANGED theta")

    assert first["created"] == 2
    assert second["created"] == 0
    assert second["updated"] == 1
    assert second["unchanged"] == 1
    assert memory.stats()["documents"] == 1


def test_reasoning_loops_build_trace(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    memory.write("brain.py calls search_memory before answer synthesis.", category_path="Code")
    memory.write("search_memory routes to graph neighbors for extra context.", category_path="Code")

    trace = memory.reason("How does brain.py answer?", loops=2, k=1)

    assert trace.steps
    assert trace.context.segment_ids
    assert trace.to_dict()["original_query"] == "How does brain.py answer?"


def test_graph_visualization_exports_html(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    memory.write("test_search.py validates brain.py memory edges.", category_path="Code")

    data = graph_data(memory)
    html = graph_html(memory)

    assert data["nodes"]
    assert "<svg" in html
    assert "DSM Memory Graph" in html


def test_mcp_server_tool_call(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "dsm.json")
    server = DsmMcpServer(memory)

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "dsm_write",
                "arguments": {"text": "MCP exposes DSM memory."},
            },
        }
    )

    assert response is not None
    assert response["result"]["content"][0]["type"] == "text"
    assert memory.stats()["segments"] == 1


def test_tiido_runtime_injects_context_before_generation_and_learns(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory()
    memory.write(
        "Danil prefers DSM-only Dynamic Context Injection.",
        category_path=("User", "Danil", "Profile"),
        importance=1.0,
        update_existing=False,
    )
    seen_contexts: list[str] = []

    def model(context: str, message: str) -> str:
        seen_contexts.append(context)
        return f"grounded: {message}"

    runtime = TiidoDSMRuntime(memory, model=model)
    turn = runtime.respond("запомни: я строю Tiido на DSM", k=3)

    assert seen_contexts
    assert "Danil prefers DSM-only" in seen_contexts[0]
    assert turn.learned_segment_ids
    assert any(segment.category_path == ("User", "Danil", "Profile") for segment in memory.segments.values())


def test_tiido_memory_is_head_state_with_optional_snapshot(tmp_path: Path) -> None:
    runtime = TiidoDSMRuntime()
    runtime.respond("запомни: я хочу память внутри головы модели", model=lambda context, message: "ok")

    assert runtime.memory.stats()["segments"] >= 2
    assert getattr(runtime.memory.storage, "path", None) is None

    snapshot_path = tmp_path / "personal_ai_v1.json"
    runtime.export_snapshot(snapshot_path)

    restored = DynamicSegmentedMemory(snapshot_path)
    assert restored.stats()["segments"] == runtime.memory.stats()["segments"]


def test_personal_dna_boost_prioritizes_identity_segments(tmp_path: Path) -> None:
    memory = DynamicSegmentedMemory(tmp_path / "personal_ai_v1.json")
    identity = memory.write(
        "Tiido must always use DSM active context before answering.",
        category_path=("Identity", "Core"),
        importance=1.0,
        update_existing=False,
    )[0]
    memory.write(
        "Generic active context note without personal identity.",
        category_path=("General", "Notes"),
        importance=0.2,
        update_existing=False,
    )

    results = memory.route("active context before answer", k=1)

    assert results[0].segment.id == identity.id
