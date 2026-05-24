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
        """Retrieve memory context for task (legacy string format for backward compatibility)."""
        structured = self.recall_structured(task)
        return structured["full_context"]

    def recall_structured(self, task: str) -> dict:
        """Retrieve structured memory context with separate sections for better LLM prompting."""
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

        # 2. Query trace memory (Trace Replay) - похожие решения
        # ✅ OPTIMIZE: Limit to 2 traces instead of 3
        traces = self.trace_memory.find_similar_traces(task, embedding, limit=2)
        similar_solutions = []
        trace_replay_context = ""
        if traces:
            trace_replay_context = "\n\n=== REASONING TRACE REPLAY (Similar Past Solutions) ===\n"
            for idx, t in enumerate(traces, 1):
                trace_replay_context += f"\n[Solution {idx}] Task: {t['task']}\n"
                trace_replay_context += f"  Similarity: {t['similarity']:.2f}\n"
                trace_replay_context += f"  Tools Used: {', '.join(t['tools_used'][:3])}\n"  # ✅ Limit to 3 tools

                solution_data = {
                    "task": t['task'],
                    "similarity": t['similarity'],
                    "tools_used": t['tools_used'][:3],  # ✅ Limit to 3 tools
                    "actions": [],
                    "result": ""
                }

                if "summary" in t:
                    sum_data = t["summary"]
                    trace_replay_context += f"  Key Actions:\n"
                    # ✅ OPTIMIZE: Limit to 3 actions instead of 5
                    for act in sum_data.get("brief_actions", [])[:3]:
                        trace_replay_context += f"    * {act[:80]}\n"  # ✅ Truncate long actions
                        solution_data["actions"].append(act[:80])
                    # ✅ OPTIMIZE: Limit result to 200 chars instead of 300
                    result = sum_data.get('brief_final_answer', '')[:200]
                    trace_replay_context += f"  Result: {result}\n"
                    solution_data["result"] = result
                else:
                    trace_replay_context += f"  Actions:\n"
                    for act in t['actions'][:3]:  # ✅ Limit to 3 actions
                        trace_replay_context += f"    * {act[:80]}\n"  # ✅ Truncate
                        solution_data["actions"].append(act[:80])
                    result = t['final_answer'][:200]  # ✅ Limit to 200 chars
                    trace_replay_context += f"  Result: {result}\n"
                    solution_data["result"] = result

                similar_solutions.append(solution_data)

        # 3. Retrieve memory field state attractors - стратегии
        # ✅ OPTIMIZE: Limit to 5 associations instead of 8
        associations = self.memory_field.get_top_associations(limit=5)
        strategy_hints = []
        assoc_context = ""
        if associations:
            assoc_context = "\n\n=== MEMORYFIELD STRATEGY ATTRACTORS ===\n"
            assoc_context += "Successful phase transitions (learned from past executions):\n"
            for a in associations:
                assoc_context += f"- {a['source']} → {a['target']} (strength: {a['weight']:.3f})\n"
                strategy_hints.append({
                    "from": a['source'],
                    "to": a['target'],
                    "strength": a['weight']
                })

        # 4. RLD active genes - reasoning patterns
        rld_genes = []
        rld_context_text = ""
        if self.enabled and self.rld is not None:
            rld_context: RLDContext = self.rld.active_context(task)
            rld_context_text = rld_context.context_text
            for activated in rld_context.activated:
                gene = activated.gene
                rld_genes.append({
                    "pattern": gene.pattern,
                    "success_rate": gene.success_count / max(1, gene.activation_count),
                    "tools": gene.tools_used,
                    "weight": activated.weight
                })

        # 5. DSM active segments - project knowledge
        dsm_segments = []
        dsm_context_text = ""
        if self.enabled and self.dsm is not None:
            dsm_context: ActiveContext = self.dsm.active_context(task, k=5)
            dsm_context_text = dsm_context.context_text
            for route_result in dsm_context.selected:
                seg = route_result.segment
                dsm_segments.append({
                    "description": seg.description,
                    "category": "/".join(seg.category_path),
                    "importance": seg.priorities.importance,
                    "text_preview": seg.text[:200]
                })

        # 6. Build combined context
        combined = ""
        if rld_context_text:
            combined += rld_context_text + "\n\n"
        if dsm_context_text:
            combined += "DSM ACTIVE CONTEXT\n" + dsm_context_text + "\n\n"

        # If memory returned nothing useful, supplement with workspace files
        if not combined or ("No reasoning genes" in combined and "No active memory" in combined):
            combined += self._fallback_context(task) + "\n\n"

        combined += trace_replay_context + assoc_context

        return {
            "full_context": combined,
            "similar_solutions": similar_solutions,
            "strategy_hints": strategy_hints,
            "rld_genes": rld_genes,
            "dsm_segments": dsm_segments,
            "has_memory": bool(rld_genes or dsm_segments or similar_solutions)
        }

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
