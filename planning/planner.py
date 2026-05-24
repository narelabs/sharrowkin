"""Hierarchical planner for decomposing complex tasks into subtasks.

This module provides intelligent task decomposition with integration to RLD
for storing successful planning patterns and DSM for context management.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .task_graph import Task, TaskGraph, TaskPriority, TaskStatus
from .tracker import ProgressTracker


@dataclass
class PlanningContext:
    """Context for planning decisions."""

    goal: str
    workspace_path: Path
    available_tools: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    user_preferences: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecompositionResult:
    """Result of task decomposition."""

    subtasks: list[Task]
    dependencies: list[tuple[str, str]]  # (task_id, depends_on_id) pairs
    rationale: str = ""
    estimated_total_duration: float = 0.0


class HierarchicalPlanner:
    """Hierarchical task planner with adaptive decomposition.

    Features:
    - Multi-level task decomposition (goal → subgoals → tasks → actions)
    - Dependency analysis and parallel execution planning
    - Time estimation based on historical data
    - Integration with RLD for pattern storage
    - Adaptive replanning on failures
    """

    def __init__(
        self,
        rld_memory_path: Path | None = None,
        max_decomposition_depth: int = 2,  # ✅ OPTIMIZE: Reduced from 3 to 2
        max_tasks: int = 50,  # ✅ NEW: Limit total tasks
    ) -> None:
        self.rld_memory_path = rld_memory_path or Path(".sharrowkin/rld_plans")
        self.rld_memory_path.mkdir(parents=True, exist_ok=True)
        self.max_decomposition_depth = max_decomposition_depth
        self.max_tasks = max_tasks

        # Historical data for time estimation
        self.task_duration_history: dict[str, list[float]] = {}

    def plan(self, goal: str, context: PlanningContext) -> TaskGraph:
        """Create a hierarchical plan for achieving the goal.

        Args:
            goal: High-level goal description
            context: Planning context with constraints and preferences

        Returns:
            TaskGraph with decomposed tasks and dependencies
        """
        graph = TaskGraph()

        # Create root task
        root_task = Task(
            title=goal,
            description=f"Root goal: {goal}",
            priority=TaskPriority.CRITICAL,
            metadata={"level": 0, "is_root": True},
        )
        graph.add_task(root_task)

        # Decompose recursively
        self._decompose_task(root_task, graph, context, depth=0)

        # Analyze and optimize the plan
        self._optimize_plan(graph)

        # Store successful plan pattern in RLD
        self._store_plan_pattern(goal, graph)

        return graph

    def _decompose_task(
        self,
        task: Task,
        graph: TaskGraph,
        context: PlanningContext,
        depth: int,
    ) -> None:
        """Recursively decompose a task into subtasks."""
        if depth >= self.max_decomposition_depth:
            return

        # ✅ NEW: Check if we've reached max_tasks limit
        if len(graph.tasks) >= self.max_tasks:
            return

        # Check if we have a stored pattern for this type of task
        pattern = self._load_plan_pattern(task.title)
        if pattern:
            decomposition = self._apply_pattern(task, pattern, context)
        else:
            decomposition = self._decompose_heuristic(task, context, depth)

        # Add subtasks to graph
        for subtask in decomposition.subtasks:
            # ✅ NEW: Stop if max_tasks reached
            if len(graph.tasks) >= self.max_tasks:
                break

            subtask.metadata["level"] = depth + 1
            subtask.metadata["parent_id"] = task.id
            graph.add_task(subtask)

            # Link subtask to parent
            graph.add_dependency(task.id, subtask.id)

        # Add inter-subtask dependencies
        for task_id, depends_on_id in decomposition.dependencies:
            graph.add_dependency(task_id, depends_on_id)

        # Recursively decompose complex subtasks
        for subtask in decomposition.subtasks:
            if len(graph.tasks) >= self.max_tasks:
                break
            if self._is_complex_task(subtask):
                self._decompose_task(subtask, graph, context, depth + 1)

    def _decompose_heuristic(
        self,
        task: Task,
        context: PlanningContext,
        depth: int,
    ) -> DecompositionResult:
        """Heuristic-based task decomposition.

        This is a rule-based decomposition that can be enhanced with LLM
        or learned from RLD patterns.
        """
        subtasks = []
        dependencies = []

        # Analyze task type and decompose accordingly
        task_lower = task.title.lower()

        if "implement" in task_lower or "add feature" in task_lower:
            # Feature implementation pattern
            subtasks = [
                Task(
                    title=f"Analyze requirements for {task.title}",
                    description="Understand requirements and existing code",
                    priority=task.priority,
                    estimated_duration_seconds=300.0,
                ),
                Task(
                    title=f"Design solution for {task.title}",
                    description="Design architecture and approach",
                    priority=task.priority,
                    estimated_duration_seconds=600.0,
                ),
                Task(
                    title=f"Implement {task.title}",
                    description="Write the actual code",
                    priority=task.priority,
                    estimated_duration_seconds=1800.0,
                ),
                Task(
                    title=f"Write tests for {task.title}",
                    description="Create unit and integration tests",
                    priority=task.priority,
                    estimated_duration_seconds=900.0,
                ),
                Task(
                    title=f"Review and refactor {task.title}",
                    description="Code review and optimization",
                    priority=task.priority,
                    estimated_duration_seconds=600.0,
                ),
            ]

            # Sequential dependencies
            for i in range(len(subtasks) - 1):
                dependencies.append((subtasks[i + 1].id, subtasks[i].id))

        elif "fix bug" in task_lower or "debug" in task_lower:
            # Bug fixing pattern
            subtasks = [
                Task(
                    title=f"Reproduce bug: {task.title}",
                    description="Create minimal reproduction case",
                    priority=TaskPriority.HIGH,
                    estimated_duration_seconds=600.0,
                ),
                Task(
                    title=f"Locate root cause: {task.title}",
                    description="Debug and identify the issue",
                    priority=TaskPriority.HIGH,
                    estimated_duration_seconds=1200.0,
                ),
                Task(
                    title=f"Fix bug: {task.title}",
                    description="Implement the fix",
                    priority=TaskPriority.HIGH,
                    estimated_duration_seconds=900.0,
                ),
                Task(
                    title=f"Add regression test: {task.title}",
                    description="Ensure bug doesn't reoccur",
                    priority=TaskPriority.HIGH,
                    estimated_duration_seconds=600.0,
                ),
            ]

            # Sequential dependencies
            for i in range(len(subtasks) - 1):
                dependencies.append((subtasks[i + 1].id, subtasks[i].id))

        elif "refactor" in task_lower:
            # Refactoring pattern
            subtasks = [
                Task(
                    title=f"Analyze code structure: {task.title}",
                    description="Understand current implementation",
                    priority=task.priority,
                    estimated_duration_seconds=600.0,
                ),
                Task(
                    title=f"Identify improvements: {task.title}",
                    description="Find refactoring opportunities",
                    priority=task.priority,
                    estimated_duration_seconds=900.0,
                ),
                Task(
                    title=f"Refactor code: {task.title}",
                    description="Apply refactoring changes",
                    priority=task.priority,
                    estimated_duration_seconds=1800.0,
                ),
                Task(
                    title=f"Verify tests pass: {task.title}",
                    description="Ensure no regressions",
                    priority=task.priority,
                    estimated_duration_seconds=300.0,
                ),
            ]

            # Sequential dependencies
            for i in range(len(subtasks) - 1):
                dependencies.append((subtasks[i + 1].id, subtasks[i].id))

        else:
            # Generic decomposition
            subtasks = [
                Task(
                    title=f"Analyze: {task.title}",
                    description="Understand the task requirements",
                    priority=task.priority,
                    estimated_duration_seconds=300.0,
                ),
                Task(
                    title=f"Execute: {task.title}",
                    description="Perform the main work",
                    priority=task.priority,
                    estimated_duration_seconds=1200.0,
                ),
                Task(
                    title=f"Verify: {task.title}",
                    description="Check the results",
                    priority=task.priority,
                    estimated_duration_seconds=300.0,
                ),
            ]

            # Sequential dependencies
            for i in range(len(subtasks) - 1):
                dependencies.append((subtasks[i + 1].id, subtasks[i].id))

        total_duration = sum(t.estimated_duration_seconds or 0.0 for t in subtasks)

        return DecompositionResult(
            subtasks=subtasks,
            dependencies=dependencies,
            rationale=f"Decomposed using heuristic pattern for task type",
            estimated_total_duration=total_duration,
        )

    def _is_complex_task(self, task: Task) -> bool:
        """Determine if a task needs further decomposition."""
        # Tasks with estimated duration > 30 minutes are considered complex
        if task.estimated_duration_seconds and task.estimated_duration_seconds > 1800:
            return True

        # Tasks with certain keywords are complex
        complex_keywords = ["implement", "refactor", "migrate", "integrate"]
        return any(keyword in task.title.lower() for keyword in complex_keywords)

    def _optimize_plan(self, graph: TaskGraph) -> None:
        """Optimize the plan for parallel execution and efficiency."""
        # Identify tasks that can be parallelized
        execution_order = graph.get_execution_order()

        # Adjust priorities based on critical path
        critical_path = graph.get_critical_path()
        for task_id in critical_path:
            task = graph.get_task(task_id)
            if task and task.priority.value < TaskPriority.HIGH.value:
                task.priority = TaskPriority.HIGH

    def _store_plan_pattern(self, goal: str, graph: TaskGraph) -> None:
        """Store successful plan pattern in RLD memory."""
        pattern = {
            "goal": goal,
            "timestamp": datetime.now().isoformat(),
            "task_count": len(graph.tasks),
            "structure": self._extract_plan_structure(graph),
        }

        # Create a hash of the goal type for pattern matching
        goal_type = self._extract_goal_type(goal)
        pattern_file = self.rld_memory_path / f"{goal_type}.json"

        try:
            pattern_file.write_text(json.dumps(pattern, indent=2))
        except Exception as e:
            print(f"Warning: Could not store plan pattern: {e}")

    def _load_plan_pattern(self, goal: str) -> dict[str, Any] | None:
        """Load a stored plan pattern from RLD memory."""
        goal_type = self._extract_goal_type(goal)
        pattern_file = self.rld_memory_path / f"{goal_type}.json"

        if not pattern_file.exists():
            return None

        try:
            return json.loads(pattern_file.read_text())
        except Exception:
            return None

    def _extract_goal_type(self, goal: str) -> str:
        """Extract goal type for pattern matching."""
        goal_lower = goal.lower()
        if "implement" in goal_lower or "add" in goal_lower:
            return "feature_implementation"
        elif "fix" in goal_lower or "bug" in goal_lower:
            return "bug_fix"
        elif "refactor" in goal_lower:
            return "refactoring"
        elif "test" in goal_lower:
            return "testing"
        else:
            return "generic"

    def _extract_plan_structure(self, graph: TaskGraph) -> dict[str, Any]:
        """Extract the structure of a plan for pattern storage."""
        return {
            "execution_levels": len(graph.get_execution_order()),
            "max_parallelism": max(len(level) for level in graph.get_execution_order()) if graph.tasks else 0,
            "critical_path_length": len(graph.get_critical_path()),
        }

    def _apply_pattern(
        self,
        task: Task,
        pattern: dict[str, Any],
        context: PlanningContext,
    ) -> DecompositionResult:
        """Apply a stored pattern to decompose a task."""
        # For now, fall back to heuristic decomposition
        # In the future, this can use the pattern structure
        return self._decompose_heuristic(task, context, 0)

    def replan(
        self,
        graph: TaskGraph,
        failed_task: Task,
        context: PlanningContext,
    ) -> TaskGraph:
        """Replan after a task failure.

        Analyzes the failure and creates an alternative plan.
        """
        # Create a new graph with the failed task replaced
        new_graph = TaskGraph()

        # Copy all tasks except the failed one and its descendants
        failed_descendants = self._get_descendants(graph, failed_task.id)
        for task_id, task in graph.tasks.items():
            if task_id not in failed_descendants and task_id != failed_task.id:
                new_graph.add_task(task)

        # Create alternative approach for the failed task
        alternative_task = Task(
            title=f"Alternative: {failed_task.title}",
            description=f"Alternative approach after failure: {failed_task.error_message}",
            priority=failed_task.priority,
            metadata={**failed_task.metadata, "is_alternative": True},
        )
        new_graph.add_task(alternative_task)

        # Decompose the alternative task
        self._decompose_task(alternative_task, new_graph, context, depth=0)

        return new_graph

    def _get_descendants(self, graph: TaskGraph, task_id: str) -> set[str]:
        """Get all descendant tasks (tasks that depend on this task)."""
        descendants = set()
        to_visit = [task_id]

        while to_visit:
            current = to_visit.pop()
            task = graph.get_task(current)
            if task:
                for blocked_id in task.blocks:
                    if blocked_id not in descendants:
                        descendants.add(blocked_id)
                        to_visit.append(blocked_id)

        return descendants
