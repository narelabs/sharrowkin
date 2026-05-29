"""Memory Bridge - Integration layer for DSM, RLD, NARE-Field."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

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
    def __init__(self, workspace: Path | str, config: AgentConfig | None = None) -> None:
        self.workspace = Path(workspace) if isinstance(workspace, str) else workspace
        self.config = config or load_config()
        # Ensure base .sharrowkin is used, but paths can be overridden
        self.memory_dir = self.workspace / ".sharrowkin"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.disabled_reason = ""
        self.rld = None
        self.dsm = None
        self._closed = False  # ✅ NEW: Track if resources are closed

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

    def __del__(self):
        """✅ NEW: Cleanup resources on deletion."""
        self.close()

    def close(self):
        """✅ NEW: Explicitly close all memory resources and save state."""
        if self._closed:
            return

        try:
            # Cleanup old segments before saving
            if self.dsm is not None:
                try:
                    # Prune low-priority segments and compress similar ones
                    stats = self.dsm.maintain(
                        max_segments=1000,  # Keep max 1000 segments
                        min_priority=0.1,   # Remove segments with priority < 0.1
                        compress_similarity=0.78
                    )
                    print(f"[MemoryBridge] DSM maintenance: {stats}")
                except Exception as e:
                    print(f"[MemoryBridge] DSM maintenance error: {e}")

            # Save all memory systems
            if self.dsm is not None:
                self.dsm.save()
            if self.rld is not None:
                self.rld.save()
            if self.memory_field is not None:
                self.memory_field.save()
            if self.trace_memory is not None:
                self.trace_memory.save()

            # Close Qdrant connections properly
            from memory.db_config import close_qdrant_client
            close_qdrant_client()

            # Clear large data structures to free memory
            if self.dsm is not None:
                self.dsm.segments.clear()
            if self.rld is not None and hasattr(self.rld, 'genes'):
                self.rld.genes.clear()
            if self.trace_memory is not None:
                # Keep only last 50 traces in memory
                if len(self.trace_memory.traces) > 50:
                    self.trace_memory.traces = self.trace_memory.traces[-50:]

            self._closed = True
            print(f"[MemoryBridge] Resources closed and saved for {self.workspace}")
        except Exception as e:
            print(f"[MemoryBridge] Error during cleanup: {e}")

    @property
    def enabled(self) -> bool:
        return self.rld is not None and self.dsm is not None

    def recall(self, task: str) -> str:
        """Retrieve memory context for task (legacy string format for backward compatibility)."""
        structured = self.recall_structured(task)
        return structured["full_context"]

    def recall_structured(self, task: str, conversation_context: str = None) -> dict:
        """Retrieve structured memory context with separate sections for better LLM prompting.

        Args:
            task: Current task/query
            conversation_context: Recent conversation history for context
        """
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
        # ✅ OPTIMIZE: Limit to 3 traces (reduced from 5) to save context
        traces = self.trace_memory.find_similar_traces(task, embedding, limit=3)
        similar_solutions = []
        trace_replay_context = ""
        if traces:
            trace_replay_context = "\n\n=== TRACE REPLAY (Past Solutions) ===\n"
            for idx, t in enumerate(traces, 1):
                trace_replay_context += f"\n[{idx}] {t['task'][:80]}... (sim: {t['similarity']:.2f})\n"
                trace_replay_context += f"  Tools: {', '.join(t['tools_used'][:3])}\n"

                solution_data = {
                    "task": t['task'],
                    "similarity": t['similarity'],
                    "tools_used": t['tools_used'][:3],
                    "actions": [],
                    "result": ""
                }

                if "summary" in t:
                    sum_data = t["summary"]
                    trace_replay_context += f"  Actions:\n"
                    # ✅ OPTIMIZE: Reduced to 3 actions, 100 chars each
                    for act in sum_data.get("brief_actions", [])[:3]:
                        trace_replay_context += f"    • {act[:100]}\n"
                        solution_data["actions"].append(act[:100])
                    # ✅ OPTIMIZE: Reduced result to 300 chars
                    result = sum_data.get('brief_final_answer', '')[:300]
                    trace_replay_context += f"  Result: {result}\n"
                    solution_data["result"] = result
                else:
                    trace_replay_context += f"  Actions:\n"
                    for act in t['actions'][:3]:
                        trace_replay_context += f"    • {act[:100]}\n"
                        solution_data["actions"].append(act[:100])
                    result = t['final_answer'][:300]
                    trace_replay_context += f"  Result: {result}\n"
                    solution_data["result"] = result

                similar_solutions.append(solution_data)

        # 3. Retrieve memory field state attractors - стратегии
        # ✅ OPTIMIZE: Limit to 3 associations (reduced from 5)
        associations = self.memory_field.get_top_associations(limit=3)
        strategy_hints = []
        assoc_context = ""
        if associations:
            assoc_context = "\n\n=== STRATEGY ATTRACTORS ===\n"
            for a in associations:
                assoc_context += f"- {a['source']} → {a['target']} ({a['weight']:.2f})\n"
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
                # Use task_context instead of pattern (ReasoningGene attribute)
                pattern = gene.task_context if hasattr(gene, 'task_context') else str(gene)
                # Use stats.success_rate instead of calculating manually
                success_rate = gene.stats.success_rate if hasattr(gene, 'stats') else 0.5
                rld_genes.append({
                    "pattern": pattern,
                    "success_rate": success_rate,
                    "tools": gene.tools_used,
                    "weight": activated.weight
                })

        # 5. DSM active segments - project knowledge
        dsm_segments = []
        dsm_context_text = ""
        if self.enabled and self.dsm is not None:
            dsm_context: ActiveContext = self.dsm.active_context(task, k=5)  # ✅ Reduced from 10 to 5
            dsm_context_text = dsm_context.context_text
            for route_result in dsm_context.selected:
                seg = route_result.segment
                dsm_segments.append({
                    "description": seg.description,
                    "category": "/".join(seg.category_path),
                    "importance": seg.priorities.importance,
                    "text_preview": seg.text[:150]  # ✅ Reduced from 200 to 150
                })

        # 6. Build combined context
        combined = ""

        # ✅ NEW: Add conversation context if provided
        if conversation_context:
            combined += "=== RECENT CONVERSATION ===\n"
            combined += conversation_context + "\n\n"

        if rld_context_text:
            combined += rld_context_text + "\n\n"
        if dsm_context_text:
            combined += "DSM ACTIVE CONTEXT\n" + dsm_context_text + "\n\n"

        # If memory returned nothing useful, supplement with workspace files
        if not combined or ("No reasoning genes" in combined and "No active memory" in combined):
            combined += self._fallback_context(task) + "\n\n"

        combined += trace_replay_context + assoc_context

        # ✅ NEW: Log context size and truncate if needed
        context_length = len(combined)
        estimated_tokens = context_length // 4  # Rough estimate: 1 token ≈ 4 chars

        logger.info(f"Built memory context: {context_length} chars (~{estimated_tokens} tokens)")
        if conversation_context:
            logger.info(f"  - Conversation context: {len(conversation_context)} chars")
        if rld_context_text:
            logger.info(f"  - RLD context: {len(rld_context_text)} chars")
        if dsm_context_text:
            logger.info(f"  - DSM context: {len(dsm_context_text)} chars")

        # ✅ NEW: Truncate if context is too large (>12000 tokens ≈ 48000 chars)
        MAX_CONTEXT_CHARS = 48000  # Reduced from 64000 to fit better in LLM context
        if context_length > MAX_CONTEXT_CHARS:
            logger.warning(f"Context too large ({context_length} chars), truncating to {MAX_CONTEXT_CHARS}")
            combined = combined[:MAX_CONTEXT_CHARS] + "\n\n[... context truncated ...]"

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

        # ✅ NEW: Write successful solution to DSM for future recall
        if self.enabled and self.dsm is not None:
            # Determine category based on tools used
            category_path = ("Solutions", "General")
            if "pytest" in tools_used or "test" in task.lower():
                category_path = ("Solutions", "Testing")
            elif "github" in " ".join(tools_used):
                category_path = ("Solutions", "GitHub")
            elif any(tool in tools_used for tool in ["file_writer", "file_editor"]):
                category_path = ("Solutions", "Code Changes")
            elif "terminal" in tools_used:
                category_path = ("Solutions", "Terminal")

            # Build solution description
            solution_text = f"Task: {task}\n\n"
            solution_text += f"Tools: {', '.join(tools_used[:5])}\n\n"
            if changed_files:
                solution_text += f"Changed files: {', '.join(changed_files[:5])}\n\n"
            solution_text += f"Actions:\n"
            for action in actions[:5]:
                solution_text += f"- {action[:200]}\n"
            solution_text += f"\nResult: {final_answer[:500]}"

            # Write to DSM with importance based on complexity
            importance = min(0.8, 0.5 + len(actions) * 0.05 + len(tools_used) * 0.03)

            self.dsm.write(
                solution_text,
                description=f"Solution: {task[:100]}",
                category_path=category_path,
                importance=importance,
                metadata={
                    "source": "sharrowkin_commit",
                    "tools_used": tools_used[:5],
                    "changed_files": changed_files[:5] if changed_files else []
                }
            )
            self.dsm.save()
            logger.info(f"Saved solution to DSM: {category_path}, importance={importance:.2f}")

    def learn_failure(
        self,
        *,
        task: str,
        states: list[str],
        actions: list[str],
        error_message: str,
        tools_used: list[str],
        changed_files: list[str] | None = None,
    ) -> None:
        """Record a failed attempt for learning and preventing repeated errors.

        Args:
            task: The task that failed
            states: List of state descriptions during execution
            actions: List of actions taken
            error_message: The error that occurred
            tools_used: Tools that were used
            changed_files: Files that were modified (if any)
        """
        logger.warning(f"Recording failure for task: {task[:100]}...")

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

        # Store failed trace in trace memory
        energy_used = 1.0 + len(states) * 0.15 + len(actions) * 0.35
        self.trace_memory.add_trace(
            task=task,
            states=states,
            actions=actions,
            final_answer=f"FAILED: {error_message}",
            success=False,  # ✅ Mark as failure
            tools_used=tools_used,
            energy_used=energy_used,
            task_embedding=embedding
        )

        # Update MemoryField with negative reinforcement
        # This weakens the phase transitions that led to failure
        if len(states) >= 2:
            self.memory_field.update_symbolic("Reason", "Stabilize", success=False)
            self.memory_field.update_symbolic("Stabilize", "Commit", success=False)

        logger.info(f"Failure recorded in TraceMemory. Total traces: {len(self.trace_memory.traces)}")

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
