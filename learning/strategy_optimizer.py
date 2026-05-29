"""Strategy optimizer for learning from successful and failed approaches.

Analyzes which strategies work best for different types of tasks and adapts
the agent's approach over time.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class Strategy:
    """A strategy for solving a particular type of task."""
    name: str
    task_pattern: str  # Regex or keyword pattern
    tools_sequence: List[str]  # Typical tool sequence
    success_rate: float
    avg_iterations: float
    total_uses: int
    last_used: float
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Strategy:
        """Create from dictionary."""
        return cls(**data)


class StrategyOptimizer:
    """Learns and optimizes strategies for different task types.

    Tracks which approaches work best for:
    - Bug fixes
    - Feature additions
    - Refactoring
    - Testing
    - Documentation
    """

    def __init__(self, workspace: Path):
        """Initialize strategy optimizer.

        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.storage_dir = workspace / ".sharrowkin" / "learning"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.storage_dir / "strategies.json"

        # Strategy database
        self.strategies: Dict[str, Strategy] = {}

        # Performance tracking
        self.task_history: List[Dict[str, Any]] = []

        # Load existing strategies
        self._load()

    def record_task(
        self,
        task: str,
        tools_used: List[str],
        iterations: int,
        success: bool,
        duration_seconds: float
    ) -> None:
        """Record a completed task for learning.

        Args:
            task: Task description
            tools_used: Tools used in sequence
            iterations: Number of iterations
            success: Whether task succeeded
            duration_seconds: Time taken
        """
        # Classify task type
        task_type = self._classify_task(task)

        # Record in history
        self.task_history.append({
            "task": task,
            "task_type": task_type,
            "tools_used": tools_used,
            "iterations": iterations,
            "success": success,
            "duration": duration_seconds,
            "timestamp": time.time()
        })

        # Update or create strategy
        if task_type in self.strategies:
            strategy = self.strategies[task_type]

            # Update success rate (exponential moving average)
            alpha = 0.3  # Learning rate
            strategy.success_rate = (
                alpha * (1.0 if success else 0.0) +
                (1 - alpha) * strategy.success_rate
            )

            # Update average iterations
            strategy.avg_iterations = (
                alpha * iterations +
                (1 - alpha) * strategy.avg_iterations
            )

            strategy.total_uses += 1
            strategy.last_used = time.time()

            # Update tool sequence if this was successful
            if success and tools_used:
                strategy.tools_sequence = tools_used

        else:
            # Create new strategy
            self.strategies[task_type] = Strategy(
                name=task_type,
                task_pattern=task_type,
                tools_sequence=tools_used if success else [],
                success_rate=1.0 if success else 0.0,
                avg_iterations=float(iterations),
                total_uses=1,
                last_used=time.time()
            )

        # Save after each update
        self._save()

    def get_recommended_strategy(self, task: str) -> Optional[Strategy]:
        """Get recommended strategy for a task.

        Args:
            task: Task description

        Returns:
            Best matching strategy or None
        """
        task_type = self._classify_task(task)

        if task_type in self.strategies:
            return self.strategies[task_type]

        # Find similar strategy
        for strategy in self.strategies.values():
            if strategy.success_rate > 0.5 and strategy.total_uses >= 3:
                # Check if task patterns overlap
                if any(keyword in task.lower() for keyword in strategy.task_pattern.lower().split()):
                    return strategy

        return None

    def get_top_strategies(self, limit: int = 5) -> List[Strategy]:
        """Get top performing strategies.

        Args:
            limit: Maximum number of strategies

        Returns:
            List of top strategies sorted by success rate
        """
        strategies = list(self.strategies.values())

        # Filter strategies with enough data
        strategies = [s for s in strategies if s.total_uses >= 3]

        # Sort by success rate
        strategies.sort(key=lambda s: s.success_rate, reverse=True)

        return strategies[:limit]

    def get_statistics(self) -> Dict[str, Any]:
        """Get learning statistics.

        Returns:
            Dictionary with statistics
        """
        if not self.task_history:
            return {
                "total_tasks": 0,
                "success_rate": 0.0,
                "avg_iterations": 0.0,
                "strategies_learned": 0
            }

        total_tasks = len(self.task_history)
        successful_tasks = sum(1 for t in self.task_history if t["success"])
        total_iterations = sum(t["iterations"] for t in self.task_history)

        return {
            "total_tasks": total_tasks,
            "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0.0,
            "avg_iterations": total_iterations / total_tasks if total_tasks > 0 else 0.0,
            "strategies_learned": len(self.strategies),
            "top_strategies": [s.name for s in self.get_top_strategies(3)]
        }

    def _classify_task(self, task: str) -> str:
        """Classify task into a type.

        Args:
            task: Task description

        Returns:
            Task type string
        """
        task_lower = task.lower()

        # Bug fix patterns
        if any(kw in task_lower for kw in ["fix", "bug", "error", "исправ", "ошибк"]):
            return "bug_fix"

        # Feature addition patterns
        if any(kw in task_lower for kw in ["add", "create", "implement", "добав", "созда", "реализ"]):
            return "feature_addition"

        # Refactoring patterns
        if any(kw in task_lower for kw in ["refactor", "improve", "optimize", "рефактор", "улучш", "оптимиз"]):
            return "refactoring"

        # Testing patterns
        if any(kw in task_lower for kw in ["test", "тест"]):
            return "testing"

        # Documentation patterns
        if any(kw in task_lower for kw in ["document", "doc", "comment", "документ", "коммент"]):
            return "documentation"

        # Analysis patterns
        if any(kw in task_lower for kw in ["analyze", "review", "check", "анализ", "провер"]):
            return "analysis"

        return "general"

    def _save(self) -> None:
        """Save strategies to disk."""
        try:
            data = {
                "strategies": {
                    name: strategy.to_dict()
                    for name, strategy in self.strategies.items()
                },
                "task_history": self.task_history[-100:],  # Keep last 100
                "saved_at": time.time()
            }

            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[StrategyOptimizer] Error saving: {e}")

    def _load(self) -> None:
        """Load strategies from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Restore strategies
            for name, strategy_data in data.get("strategies", {}).items():
                self.strategies[name] = Strategy.from_dict(strategy_data)

            # Restore history
            self.task_history = data.get("task_history", [])

            print(f"[StrategyOptimizer] Loaded {len(self.strategies)} strategies")
        except Exception as e:
            print(f"[StrategyOptimizer] Error loading: {e}")
