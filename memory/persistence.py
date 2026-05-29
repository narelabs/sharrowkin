"""Persistent memory checkpoint management for Sharrowkin agent."""

from __future__ import annotations

import json
import signal
import time
from pathlib import Path
from typing import Optional
import asyncio


class PersistentMemoryManager:
    """Manages checkpoint saving and restoration for memory systems."""

    def __init__(self, workspace: Path, checkpoint_interval: int = 10):
        """
        Args:
            workspace: Workspace directory
            checkpoint_interval: Save checkpoint every N iterations
        """
        self.workspace = workspace
        self.checkpoint_dir = workspace / ".sharrowkin" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_interval = checkpoint_interval
        self.iteration_count = 0
        self.last_checkpoint_time = time.time()
        self._shutdown_handler_registered = False

    def register_shutdown_handler(self, memory_bridge):
        """Register signal handler for graceful shutdown."""
        if self._shutdown_handler_registered:
            return

        def shutdown_handler(signum, frame):
            print(f"\n[Checkpoint] Received signal {signum}, saving checkpoint...")
            self.save_checkpoint_sync(memory_bridge)
            print(f"[Checkpoint] Checkpoint saved, exiting")
            exit(0)

        # Register handlers for SIGTERM and SIGINT
        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)
        self._shutdown_handler_registered = True
        print(f"[Checkpoint] Shutdown handlers registered")

    async def save_checkpoint(self, memory_bridge, session_id: str = "default") -> Path:
        """Save memory checkpoint asynchronously.

        Args:
            memory_bridge: MemoryBridge instance to save
            session_id: Session identifier

        Returns:
            Path to saved checkpoint
        """
        return await asyncio.to_thread(self.save_checkpoint_sync, memory_bridge, session_id)

    def save_checkpoint_sync(self, memory_bridge, session_id: str = "default") -> Path:
        """Save memory checkpoint synchronously.

        Args:
            memory_bridge: MemoryBridge instance to save
            session_id: Session identifier

        Returns:
            Path to saved checkpoint
        """
        timestamp = int(time.time())
        checkpoint_file = self.checkpoint_dir / f"checkpoint_{session_id}_{timestamp}.json"

        checkpoint_data = {
            "session_id": session_id,
            "timestamp": timestamp,
            "workspace": str(self.workspace),
            "iteration_count": self.iteration_count,
            "memory_stats": {}
        }

        # Save DSM state
        if memory_bridge.dsm is not None:
            try:
                memory_bridge.dsm.save()
                checkpoint_data["memory_stats"]["dsm_segments"] = len(memory_bridge.dsm.segments)
                checkpoint_data["dsm_path"] = str(memory_bridge.memory_dir / "dsm_memory.json")
            except Exception as e:
                print(f"[Checkpoint] Error saving DSM: {e}")

        # Save RLD state
        if memory_bridge.rld is not None:
            try:
                memory_bridge.rld.save()
                checkpoint_data["memory_stats"]["rld_genes"] = len(memory_bridge.rld.genes) if hasattr(memory_bridge.rld, 'genes') else 0
                checkpoint_data["rld_path"] = str(memory_bridge.memory_dir / "rld_genes.json")
            except Exception as e:
                print(f"[Checkpoint] Error saving RLD: {e}")

        # Save TraceMemory state
        if memory_bridge.trace_memory is not None:
            try:
                memory_bridge.trace_memory.save()
                checkpoint_data["memory_stats"]["traces"] = len(memory_bridge.trace_memory.traces)
                checkpoint_data["trace_path"] = str(memory_bridge.memory_dir / "trace_memory.json")
            except Exception as e:
                print(f"[Checkpoint] Error saving TraceMemory: {e}")

        # Save MemoryField state
        if memory_bridge.memory_field is not None:
            try:
                memory_bridge.memory_field.save()
                checkpoint_data["memory_stats"]["field_associations"] = len(memory_bridge.memory_field.get_top_associations(limit=100))
                checkpoint_data["field_path"] = str(memory_bridge.memory_dir / "memory_field.json")
            except Exception as e:
                print(f"[Checkpoint] Error saving MemoryField: {e}")

        # Write checkpoint metadata
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2)

        # Update latest checkpoint symlink
        latest_link = self.checkpoint_dir / f"latest_{session_id}.json"
        if latest_link.exists():
            latest_link.unlink()
        try:
            latest_link.symlink_to(checkpoint_file.name)
        except OSError:
            # Symlinks may not work on Windows, copy instead
            import shutil
            shutil.copy(checkpoint_file, latest_link)

        self.last_checkpoint_time = time.time()
        print(f"[Checkpoint] Saved to {checkpoint_file}")
        print(f"[Checkpoint] Stats: {checkpoint_data['memory_stats']}")

        # Cleanup old checkpoints (keep last 5)
        self._cleanup_old_checkpoints(session_id, keep=5)

        return checkpoint_file

    async def restore_checkpoint(self, session_id: str = "default") -> Optional[dict]:
        """Restore memory checkpoint asynchronously.

        Args:
            session_id: Session identifier

        Returns:
            Checkpoint metadata or None if not found
        """
        return await asyncio.to_thread(self.restore_checkpoint_sync, session_id)

    def restore_checkpoint_sync(self, session_id: str = "default") -> Optional[dict]:
        """Restore memory checkpoint synchronously.

        Args:
            session_id: Session identifier

        Returns:
            Checkpoint metadata or None if not found
        """
        latest_link = self.checkpoint_dir / f"latest_{session_id}.json"

        if not latest_link.exists():
            print(f"[Checkpoint] No checkpoint found for session {session_id}")
            return None

        try:
            with open(latest_link, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)

            print(f"[Checkpoint] Restored from {latest_link}")
            print(f"[Checkpoint] Stats: {checkpoint_data.get('memory_stats', {})}")

            self.iteration_count = checkpoint_data.get("iteration_count", 0)
            return checkpoint_data

        except Exception as e:
            print(f"[Checkpoint] Error restoring checkpoint: {e}")
            return None

    def should_save_checkpoint(self) -> bool:
        """Check if it's time to save a checkpoint.

        Returns:
            True if checkpoint should be saved
        """
        self.iteration_count += 1
        return self.iteration_count % self.checkpoint_interval == 0

    def _cleanup_old_checkpoints(self, session_id: str, keep: int = 5):
        """Remove old checkpoints, keeping only the most recent ones.

        Args:
            session_id: Session identifier
            keep: Number of checkpoints to keep
        """
        pattern = f"checkpoint_{session_id}_*.json"
        checkpoints = sorted(
            self.checkpoint_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # Remove old checkpoints
        for checkpoint in checkpoints[keep:]:
            try:
                checkpoint.unlink()
                print(f"[Checkpoint] Removed old checkpoint: {checkpoint.name}")
            except Exception as e:
                print(f"[Checkpoint] Error removing checkpoint: {e}")

    def get_checkpoint_info(self, session_id: str = "default") -> Optional[dict]:
        """Get information about the latest checkpoint.

        Args:
            session_id: Session identifier

        Returns:
            Checkpoint info or None
        """
        latest_link = self.checkpoint_dir / f"latest_{session_id}.json"

        if not latest_link.exists():
            return None

        try:
            with open(latest_link, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
