"""Phase 5: Commit - Memory consolidation and learning.

Handles saving successful patterns to memory systems (DSM, RLD, TraceMemory, MemoryField).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import asyncio

from memory import MemoryBridge


class CommitModule:
    """Phase 5: Commit - Save successful patterns to memory."""

    def __init__(self, config: Any):
        self.config = config

    async def commit(
        self,
        memory: MemoryBridge,
        task: str,
        states: list[str],
        actions: list[str],
        changed_files: list[str],
        success: bool,
        utility: float = 0.7,
        ui_delays_enabled: bool = False
    ) -> dict[str, Any]:
        """Commit successful execution to memory.

        Returns:
            Dictionary with commit status
        """
        if ui_delays_enabled:
            await asyncio.sleep(0.2)

        if not memory.enabled:
            return {"committed": False, "reason": "Memory disabled"}

        # Write to DSM
        dsm_written = False
        if memory.dsm:
            try:
                memory.dsm.write(
                    text=f"Task: {task}\nActions: {', '.join(actions[-3:])}",
                    description=f"Completed task: {task[:100]}",
                    category_path="agent/tasks",
                    importance=utility,
                )
                dsm_written = True
            except Exception as e:
                print(f"[Commit] DSM write failed: {e}")

        # Write to RLD
        rld_written = False
        if memory.rld:
            try:
                memory.rld.observe(
                    task=task,
                    states=states,
                    actions=actions,
                    success=success,
                    utility=utility,
                    tools_used=["file_edit", "syntax_check"],
                )
                rld_written = True
            except Exception as e:
                print(f"[Commit] RLD write failed: {e}")

        # Update MemoryField phase transitions
        field_updated = False
        if memory.memory_field and len(states) >= 2:
            try:
                for i in range(len(states) - 1):
                    memory.memory_field.update_symbolic(
                        state_from=states[i],
                        state_to=states[i + 1],
                        success=success,
                    )
                field_updated = True
            except Exception as e:
                print(f"[Commit] MemoryField update failed: {e}")

        # Write to TraceMemory
        trace_written = False
        if memory.trace_memory:
            try:
                memory.trace_memory.record_trace(
                    task=task,
                    states=states,
                    actions=actions,
                    success=success,
                    changed_files=changed_files,
                )
                trace_written = True
            except Exception as e:
                print(f"[Commit] TraceMemory write failed: {e}")

        return {
            "committed": True,
            "dsm_written": dsm_written,
            "rld_written": rld_written,
            "field_updated": field_updated,
            "trace_written": trace_written,
        }
