"""Task graph for managing dependencies and execution order.

This module provides a directed acyclic graph (DAG) for task dependencies,
enabling parallel execution of independent tasks and proper ordering of
dependent tasks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    READY = "ready"  # All dependencies satisfied
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Has unsatisfied dependencies
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = 5
    HIGH = 4
    NORMAL = 3
    LOW = 2
    DEFERRED = 1


@dataclass
class Task:
    """Represents a single task in the execution graph."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL

    # Dependencies
    depends_on: set[str] = field(default_factory=set)  # Task IDs this task depends on
    blocks: set[str] = field(default_factory=set)  # Task IDs that depend on this task

    # Execution metadata
    estimated_duration_seconds: float | None = None
    actual_duration_seconds: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Error tracking
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3

    # Additional context
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def estimated_time(self) -> float:
        """Estimated time in minutes (for backward compatibility)."""
        if self.estimated_duration_seconds is None:
            return 0.0
        return self.estimated_duration_seconds / 60.0

    def can_execute(self, task_graph: TaskGraph) -> bool:
        """Check if all dependencies are satisfied."""
        if self.status in (TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED):
            return False

        for dep_id in self.depends_on:
            dep_task = task_graph.get_task(dep_id)
            if dep_task is None or dep_task.status != TaskStatus.COMPLETED:
                return False

        return True

    def mark_started(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now()

    def mark_completed(self) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        if self.started_at:
            self.actual_duration_seconds = (self.completed_at - self.started_at).total_seconds()

    def mark_failed(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.error_message = error
        self.retry_count += 1


class TaskGraph:
    """Directed acyclic graph for managing task dependencies."""

    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}

    def add_task(self, task: Task) -> str:
        """Add a task to the graph. Returns task ID."""
        self.tasks[task.id] = task
        return task.id

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def add_dependency(self, task_id: str, depends_on_id: str) -> bool:
        """Add a dependency: task_id depends on depends_on_id.

        Returns False if this would create a cycle.
        """
        if task_id not in self.tasks or depends_on_id not in self.tasks:
            return False

        # Check for cycle
        if self._would_create_cycle(task_id, depends_on_id):
            return False

        self.tasks[task_id].depends_on.add(depends_on_id)
        self.tasks[depends_on_id].blocks.add(task_id)
        return True

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        """Check if adding edge from_id -> to_id would create a cycle."""
        # DFS to check if there's already a path from to_id to from_id
        visited = set()

        def dfs(current: str) -> bool:
            if current == from_id:
                return True
            if current in visited:
                return False
            visited.add(current)

            task = self.tasks.get(current)
            if task is None:
                return False

            for dep_id in task.depends_on:
                if dfs(dep_id):
                    return True
            return False

        return dfs(to_id)

    def get_ready_tasks(self) -> list[Task]:
        """Get all tasks that are ready to execute (dependencies satisfied)."""
        ready = []
        for task in self.tasks.values():
            if task.can_execute(self):
                ready.append(task)

        # Sort by priority (highest first)
        ready.sort(key=lambda t: t.priority.value, reverse=True)
        return ready

    def get_blocked_tasks(self) -> list[Task]:
        """Get all tasks that are blocked by dependencies."""
        blocked = []
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING and not task.can_execute(self):
                blocked.append(task)
        return blocked

    def get_dependencies(self, task_id: str) -> set[str]:
        """Get all dependencies for a task."""
        task = self.tasks.get(task_id)
        if task is None:
            return set()
        return task.depends_on.copy()

    def get_execution_order(self) -> list[list[str]]:
        """Get tasks grouped by execution level (topological sort).

        Returns a list of lists, where each inner list contains task IDs
        that can be executed in parallel.
        """
        levels: list[list[str]] = []
        remaining = set(self.tasks.keys())

        while remaining:
            # Find tasks with no dependencies in remaining set
            current_level = []
            for task_id in remaining:
                task = self.tasks[task_id]
                if all(dep_id not in remaining for dep_id in task.depends_on):
                    current_level.append(task_id)

            if not current_level:
                # Cycle detected or all remaining tasks are blocked
                break

            levels.append(current_level)
            remaining -= set(current_level)

        return levels

    def get_critical_path(self) -> list[str]:
        """Get the critical path (longest path through the graph by duration)."""
        # Calculate longest path to each node
        longest_path: dict[str, float] = {}
        predecessor: dict[str, str | None] = {}

        for task_id in self.tasks:
            longest_path[task_id] = 0.0
            predecessor[task_id] = None

        # Process tasks in topological order
        for level in self.get_execution_order():
            for task_id in level:
                task = self.tasks[task_id]
                duration = task.estimated_duration_seconds or 0.0

                for blocked_id in task.blocks:
                    new_length = longest_path[task_id] + duration
                    if new_length > longest_path[blocked_id]:
                        longest_path[blocked_id] = new_length
                        predecessor[blocked_id] = task_id

        # Find the task with longest path
        if not longest_path:
            return []

        end_task_id = max(longest_path.items(), key=lambda x: x[1])[0]

        # Reconstruct path
        path = []
        current = end_task_id
        while current is not None:
            path.append(current)
            current = predecessor[current]

        return list(reversed(path))

    def get_statistics(self) -> dict[str, Any]:
        """Get graph statistics."""
        total = len(self.tasks)
        by_status = {}
        for status in TaskStatus:
            by_status[status.value] = sum(1 for t in self.tasks.values() if t.status == status)

        completed_tasks = [t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]
        total_duration = sum(t.actual_duration_seconds or 0.0 for t in completed_tasks)

        return {
            "total_tasks": total,
            "by_status": by_status,
            "completed_count": len(completed_tasks),
            "total_duration_seconds": total_duration,
            "average_duration_seconds": total_duration / len(completed_tasks) if completed_tasks else 0.0,
            "critical_path_length": len(self.get_critical_path()),
            "max_parallelism": max(len(level) for level in self.get_execution_order()) if self.tasks else 0,
        }

    def visualize(self) -> str:
        """Generate a simple text visualization of the graph."""
        lines = ["Task Dependency Graph:", "=" * 50]

        for level_idx, level in enumerate(self.get_execution_order()):
            lines.append(f"\nLevel {level_idx + 1} (parallel execution):")
            for task_id in level:
                task = self.tasks[task_id]
                status_symbol = {
                    TaskStatus.PENDING: "⏸",
                    TaskStatus.READY: "▶",
                    TaskStatus.IN_PROGRESS: "⏳",
                    TaskStatus.COMPLETED: "✓",
                    TaskStatus.FAILED: "✗",
                    TaskStatus.BLOCKED: "🔒",
                    TaskStatus.CANCELLED: "⊘",
                }[task.status]

                deps = f" (depends on: {', '.join(task.depends_on)})" if task.depends_on else ""
                lines.append(f"  {status_symbol} [{task.priority.name}] {task.title}{deps}")

        lines.append("\n" + "=" * 50)
        stats = self.get_statistics()
        lines.append(f"Total tasks: {stats['total_tasks']}")
        lines.append(f"Completed: {stats['completed_count']}")
        lines.append(f"Max parallelism: {stats['max_parallelism']}")

        return "\n".join(lines)
