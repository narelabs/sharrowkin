"""Phase 2: Recall - Memory retrieval and context enrichment.

Handles DSM, RLD, TraceMemory, and MemoryField retrieval.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import asyncio

from memory import MemoryBridge


class RecallModule:
    """Phase 2: Recall - Retrieve relevant memory context."""

    def __init__(self, config: Any):
        self.config = config

    async def recall(
        self,
        memory: MemoryBridge,
        task: str,
        workspace_summary: str,
        conversation_context: str = None,
        ui_delays_enabled: bool = False
    ) -> dict[str, Any]:
        """Retrieve memory context for the task.

        Args:
            memory: MemoryBridge instance
            task: Current task
            workspace_summary: Workspace summary
            conversation_context: Recent conversation history
            ui_delays_enabled: Enable UI delays

        Returns:
            Dictionary with:
            - memory_context: str (formatted context)
            - memory_context_structured: dict (raw structured data)
        """
        if ui_delays_enabled:
            await asyncio.sleep(0.2)

        if not memory.enabled:
            return {
                "memory_context": "Memory system disabled.",
                "memory_context_structured": {},
            }

        # Retrieve from all memory systems with conversation context
        context_data = memory.recall_structured(
            task=task,
            conversation_context=conversation_context
        )

        # Format as text
        memory_context = self._format_memory_context(context_data)

        return {
            "memory_context": memory_context,
            "memory_context_structured": context_data,
        }

    def _format_memory_context(self, context_data: dict[str, Any]) -> str:
        """Format structured memory context as text."""
        parts = []

        # DSM segments
        dsm_segments = context_data.get("dsm_segments", [])
        if dsm_segments:
            parts.append("## DSM Memory")
            for seg in dsm_segments[:3]:  # Limit to top 3
                parts.append(f"- {seg.get('text', '')[:200]}")

        # RLD genes
        rld_genes = context_data.get("rld_genes", [])
        if rld_genes:
            parts.append("\n## RLD Genes")
            for gene in rld_genes[:2]:  # Limit to top 2
                parts.append(f"- {gene.get('task_context', '')[:150]}")

        # Trace memory
        traces = context_data.get("traces", [])
        if traces:
            parts.append("\n## Similar Traces")
            for trace in traces[:2]:  # Limit to top 2
                parts.append(f"- {trace.get('task', '')[:150]}")

        # Memory field associations
        associations = context_data.get("associations", [])
        if associations:
            parts.append("\n## Phase Transitions")
            for assoc in associations[:5]:  # Limit to top 5
                parts.append(
                    f"- {assoc.get('source', '')} → {assoc.get('target', '')}: "
                    f"{assoc.get('weight', 0):.2f}"
                )

        return "\n".join(parts) if parts else "No relevant memory found."
