"""Memory Bridge - Integration layer for DSM, RLD, NARE-Field."""

from __future__ import annotations

from pathlib import Path

try:
    from memory.dsm.core.memory import DynamicSegmentedMemory
    from memory.dsm.core.models import ActiveContext
    from memory.rld.core import RecursiveLatentDNA
    from memory.rld.models import RLDContext
except ImportError as import_error:
    DynamicSegmentedMemory = None
    ActiveContext = None
    RecursiveLatentDNA = None
    RLDContext = None
    IMPORT_ERROR = import_error
else:
    IMPORT_ERROR = None

from config.settings import AgentConfig, load_config


class MemoryBridge:
    def __init__(self, workspace: Path, config: AgentConfig | None = None) -> None:
        self.workspace = workspace
        self.config = config or load_config()
        # Ensure base .sharrowkin is used, but paths can be overridden
        self.memory_dir = workspace / ".sharrowkin"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.disabled_reason = ""
        self.rld = None
        self.dsm = None

        # Instantiate memory field and trace memory
        from memory.field import MemoryField
        from memory.trace import TraceMemory
        self.memory_field = MemoryField(self.memory_dir / "memory_field.json", default_dim=128)
        self.trace_memory = TraceMemory(self.memory_dir / "trace_memory.json")

        if IMPORT_ERROR is not None or DynamicSegmentedMemory is None or RecursiveLatentDNA is None:
            self.disabled_reason = f"Memory modules unavailable: {IMPORT_ERROR}"
            return
        self.dsm = DynamicSegmentedMemory(self.memory_dir / "dsm_memory.json")
        self.rld = RecursiveLatentDNA(
            storage_path=self.memory_dir / "rld_genes.json",
            dsm_memory=self.dsm,
        )

    @property
    def enabled(self) -> bool:
        return self.rld is not None and self.dsm is not None

    def recall(self, task: str) -> str:
        # 1. Get query embedding dynamically
        embedding = [0.0] * 128
        if self.rld and self.rld.embedding_model:
            try:
                embedding = self.rld.embedding_model.encode(task)
            except Exception:
                from memory.dsm.indexing.embedding import HashEmbeddingModel
                embedding = HashEmbeddingModel().encode(task)
        else:
            from memory.dsm.indexing.embedding import HashEmbeddingModel
            embedding = HashEmbeddingModel().encode(task)

        # 2. Query trace memory (Trace Replay)
        traces = self.trace_memory.find_similar_traces(task, embedding, limit=2)
        trace_replay_context = ""
        if traces:
            trace_replay_context = "\n\n=== REASONING TRACE REPLAY (Matched Past Trajectories) ===\n"
            for t in traces:
                trace_replay_context += f"\n- Similar Past Task: {t['task']}\n"
                trace_replay_context += f"  Similarity: {t['similarity']}\n"
                trace_replay_context += f"  Tools Used: {', '.join(t['tools_used'])}\n"
                if "summary" in t:
                    sum_data = t["summary"]
                    trace_replay_context += f"  Key States Visited:\n"
                    for s_sum in sum_data.get("summarized_states", []):
                        trace_replay_context += f"    * {s_sum}\n"
                    trace_replay_context += f"  Key Actions:\n"
                    for act in sum_data.get("brief_actions", []):
                        trace_replay_context += f"    * {act}\n"
                    trace_replay_context += f"  Brief Final Answer:\n    {sum_data.get('brief_final_answer', '')}\n"
                else:
                    trace_replay_context += f"  Actions taken:\n"
                    for act in t['actions']:
                        trace_replay_context += f"    * {act}\n"
                    trace_replay_context += f"  Resulting Answer:\n    {t['final_answer'][:500]}...\n"

        # 3. Retrieve memory field state attractors
        associations = self.memory_field.get_top_associations(limit=5)
        assoc_context = ""
        if associations:
            assoc_context = "\n\n=== MEMORYFIELD ATTRACTOR NETWORKS ===\n"
            for a in associations:
                assoc_context += f"- Link: {a['source']} -> {a['target']} (strength: {a['weight']})\n"

        if not self.enabled:
            return self._fallback_context(task) + trace_replay_context + assoc_context
        if self.rld is None or self.dsm is None:
            return self._fallback_context(task) + trace_replay_context + assoc_context

        rld_context: RLDContext = self.rld.active_context(task)
        dsm_context: ActiveContext = self.dsm.active_context(task, k=4)
        combined = "\n\n".join(
            [
                rld_context.context_text,
                "DSM ACTIVE CONTEXT",
                dsm_context.context_text,
            ]
        )
        # If memory returned nothing useful, supplement with workspace files
        if "No reasoning genes" in combined and "No active memory" in combined:
            combined += "\n\n" + self._fallback_context(task)

        return combined + trace_replay_context + assoc_context

    def _fallback_context(self, task: str) -> str:
        """Read key workspace files as fallback when memory is empty."""
        import os
        context_parts = ["WORKSPACE FILE CONTEXT (memory is cold — bootstrapping from files)"]
        # Read README
        readme = self.workspace / "README.md"
        if readme.exists():
            try:
                text = readme.read_text(encoding="utf-8", errors="replace")[:6000]
                context_parts.append(f"--- README.md ---\n{text}")
            except Exception:
                pass
        # Read pyproject.toml or package.json
        for cfg in ("pyproject.toml", "package.json", "setup.py", "Cargo.toml"):
            cfg_path = self.workspace / cfg
            if cfg_path.exists():
                try:
                    text = cfg_path.read_text(encoding="utf-8", errors="replace")[:3000]
                    context_parts.append(f"--- {cfg} ---\n{text}")
                except Exception:
                    pass
                break
        if len(context_parts) == 1:
            context_parts.append("No README or config files found. Agent will rely on AST scan only.")
        return "\n\n".join(context_parts)

    def learn_project(self, workspace_summary: str) -> None:
        if not self.enabled or self.dsm is None:
            return
        self.dsm.write(
            workspace_summary,
            description="Workspace AST architecture summary",
            category_path=("Project", "Architecture"),
            importance=0.65,
            metadata={"source": "sharrowkin_observe"},
        )
        self.dsm.save()

    def learn_success(
        self,
        *,
        task: str,
        states: list[str],
        actions: list[str],
        final_answer: str,
        tools_used: list[str],
        changed_files: list[str] | None = None,
        workspace_summary: str | None = None,
    ) -> None:
        # Encode task for trace indexing
        embedding = [0.0] * 128
        if self.rld and self.rld.embedding_model:
            try:
                embedding = self.rld.embedding_model.encode(task)
            except Exception:
                from memory.dsm.indexing.embedding import HashEmbeddingModel
                embedding = HashEmbeddingModel().encode(task)
        else:
            from memory.dsm.indexing.embedding import HashEmbeddingModel
            embedding = HashEmbeddingModel().encode(task)

        # Store in trace memory
        energy_used = 1.0 + len(states) * 0.15 + len(actions) * 0.35
        self.trace_memory.add_trace(
            task=task,
            states=states,
            actions=actions,
            final_answer=final_answer,
            success=True,
            tools_used=tools_used,
            energy_used=energy_used,
            task_embedding=embedding
        )

        # Update MemoryField attractor weights and symbolic transitions
        if len(states) >= 2 and self.rld and self.rld.embedding_model:
            try:
                z_start = self.rld.embedding_model.encode(states[0][:3000])
                z_end = self.rld.embedding_model.encode(states[-1][:3000])
                self.memory_field.update_hebbian(z_start, z_end)
            except Exception as e:
                print(f"[MemoryBridge] Hebbian update error: {e}")

        self.memory_field.update_symbolic("Observe", "Recall", success=True)
        self.memory_field.update_symbolic("Recall", "Reason", success=True)
        self.memory_field.update_symbolic("Reason", "Stabilize", success=True)
        self.memory_field.update_symbolic("Stabilize", "Commit", success=True)

        if not self.enabled or self.rld is None or self.dsm is None:
            return

        self.rld.observe(
            task,
            states=states,
            actions=actions,
            final_answer=final_answer,
            success=True,
            utility=0.9,
            tools_used=tools_used,
            metadata={"workspace": str(self.workspace)},
        )
        self.rld.save()

        # Enhanced DSM storage with more context
        dsm_content = f"""Task: {task}

Result: {final_answer}

Files changed: {', '.join(changed_files) if changed_files else 'none'}

Actions taken:
{chr(10).join(f'- {action}' for action in actions[:10]) if actions else 'none'}

Tools used: {', '.join(set(tools_used)) if tools_used else 'none'}"""

        if workspace_summary:
            dsm_content += f"\n\nProject context:\n{workspace_summary[:500]}"

        self.dsm.update_from_interaction(
            task,
            dsm_content,
            importance=0.8,
            metadata={
                "source": "sharrowkin_success",
                "changed_files": changed_files or [],
                "tools_used": tools_used,
            },
        )
        self.dsm.save()
        if len(self.rld.trajectories) > 0 and len(self.rld.trajectories) % 5 == 0:
            self.rld.sleep(save_after=True)
