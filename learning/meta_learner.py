"""Meta-learner for tracking and improving learning performance.

Monitors the agent's learning progress and adapts learning strategies.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import deque


@dataclass
class LearningMetrics:
    """Metrics for tracking learning performance."""
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    avg_iterations: float
    avg_duration: float
    improvement_rate: float  # Rate of improvement over time
    adaptation_speed: float  # How quickly agent adapts to new patterns
    memory_utilization: float  # How well memory is being used
    strategy_diversity: int  # Number of different strategies learned
    last_updated: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LearningMetrics:
        """Create from dictionary."""
        return cls(**data)


class MetaLearner:
    """Meta-learning system for monitoring and improving learning.

    Tracks:
    - Learning progress over time
    - Effectiveness of different learning strategies
    - Adaptation to new task types
    - Memory system utilization
    """

    def __init__(self, workspace: Path):
        """Initialize meta-learner.

        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.storage_dir = workspace / ".sharrowkin" / "learning"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.storage_dir / "meta_learning.json"

        # Performance tracking
        self.metrics: Optional[LearningMetrics] = None
        self.task_timeline: deque = deque(maxlen=100)  # Last 100 tasks
        self.learning_events: List[Dict[str, Any]] = []

        # Load existing data
        self._load()

        if self.metrics is None:
            self.metrics = self._default_metrics()

    def record_task_completion(
        self,
        task: str,
        success: bool,
        iterations: int,
        duration: float,
        memory_used: bool,
        strategy_used: Optional[str] = None
    ) -> None:
        """Record a completed task for meta-learning.

        Args:
            task: Task description
            success: Whether task succeeded
            iterations: Number of iterations
            duration: Time taken in seconds
            memory_used: Whether memory was utilized
            strategy_used: Strategy name if any
        """
        # Record in timeline
        self.task_timeline.append({
            "task": task,
            "success": success,
            "iterations": iterations,
            "duration": duration,
            "memory_used": memory_used,
            "strategy": strategy_used,
            "timestamp": time.time()
        })

        # Update metrics
        self.metrics.total_tasks += 1
        if success:
            self.metrics.successful_tasks += 1
        else:
            self.metrics.failed_tasks += 1

        # Update averages (exponential moving average)
        alpha = 0.2
        self.metrics.avg_iterations = (
            alpha * iterations +
            (1 - alpha) * self.metrics.avg_iterations
        )
        self.metrics.avg_duration = (
            alpha * duration +
            (1 - alpha) * self.metrics.avg_duration
        )

        # Calculate improvement rate
        if len(self.task_timeline) >= 10:
            recent_success = sum(1 for t in list(self.task_timeline)[-10:] if t["success"])
            older_success = sum(1 for t in list(self.task_timeline)[-20:-10] if t["success"]) if len(self.task_timeline) >= 20 else 5
            self.metrics.improvement_rate = (recent_success - older_success) / 10.0

        # Update memory utilization
        if memory_used:
            self.metrics.memory_utilization = (
                alpha * 1.0 +
                (1 - alpha) * self.metrics.memory_utilization
            )
        else:
            self.metrics.memory_utilization = (
                alpha * 0.0 +
                (1 - alpha) * self.metrics.memory_utilization
            )

        self.metrics.last_updated = time.time()

        # Save after each update
        self._save()

    def record_learning_event(
        self,
        event_type: str,
        description: str,
        impact: float
    ) -> None:
        """Record a significant learning event.

        Args:
            event_type: Type of event (e.g., "new_strategy", "pattern_discovered")
            description: Event description
            impact: Estimated impact (0.0 to 1.0)
        """
        self.learning_events.append({
            "type": event_type,
            "description": description,
            "impact": impact,
            "timestamp": time.time()
        })

        # Keep only recent events
        if len(self.learning_events) > 50:
            self.learning_events = self.learning_events[-50:]

        self._save()

    def get_learning_report(self) -> str:
        """Generate a learning progress report.

        Returns:
            Markdown-formatted report
        """
        if not self.metrics:
            return "No learning data available."

        success_rate = (
            self.metrics.successful_tasks / self.metrics.total_tasks * 100
            if self.metrics.total_tasks > 0 else 0.0
        )

        report = f"""# 📊 Meta-Learning Report

## Overall Performance
- **Total Tasks**: {self.metrics.total_tasks}
- **Success Rate**: {success_rate:.1f}%
- **Average Iterations**: {self.metrics.avg_iterations:.1f}
- **Average Duration**: {self.metrics.avg_duration:.1f}s

## Learning Progress
- **Improvement Rate**: {self.metrics.improvement_rate:+.2f} (per 10 tasks)
- **Memory Utilization**: {self.metrics.memory_utilization * 100:.1f}%
- **Strategy Diversity**: {self.metrics.strategy_diversity} strategies learned

## Adaptation
- **Adaptation Speed**: {self.metrics.adaptation_speed:.2f}
"""

        # Recent trends
        if len(self.task_timeline) >= 5:
            recent_tasks = list(self.task_timeline)[-5:]
            recent_success = sum(1 for t in recent_tasks if t["success"])
            report += f"\n## Recent Performance (Last 5 Tasks)\n"
            report += f"- Success: {recent_success}/5 ({recent_success/5*100:.0f}%)\n"

            avg_recent_iterations = sum(t["iterations"] for t in recent_tasks) / len(recent_tasks)
            report += f"- Avg Iterations: {avg_recent_iterations:.1f}\n"

        # Recent learning events
        if self.learning_events:
            report += "\n## Recent Learning Events\n"
            for event in self.learning_events[-5:]:
                report += f"- **{event['type']}**: {event['description']} (impact: {event['impact']:.2f})\n"

        return report

    def get_recommendations(self) -> List[str]:
        """Get recommendations for improving learning.

        Returns:
            List of recommendations
        """
        recommendations = []

        if not self.metrics:
            return ["Insufficient data for recommendations"]

        # Check success rate
        success_rate = (
            self.metrics.successful_tasks / self.metrics.total_tasks
            if self.metrics.total_tasks > 0 else 0.0
        )

        if success_rate < 0.5:
            recommendations.append(
                "Low success rate detected. Consider analyzing failed tasks for common patterns."
            )

        # Check memory utilization
        if self.metrics.memory_utilization < 0.3:
            recommendations.append(
                "Low memory utilization. Memory systems may not be providing relevant context."
            )

        # Check improvement rate
        if self.metrics.improvement_rate < -0.1:
            recommendations.append(
                "Negative improvement trend. Review recent strategy changes."
            )

        # Check iteration count
        if self.metrics.avg_iterations > 5.0:
            recommendations.append(
                "High average iterations. Consider improving initial strategy selection."
            )

        # Check strategy diversity
        if self.metrics.strategy_diversity < 3 and self.metrics.total_tasks > 20:
            recommendations.append(
                "Low strategy diversity. Agent may be stuck in local optimum."
            )

        if not recommendations:
            recommendations.append("Learning performance is good. Continue current approach.")

        return recommendations

    def update_strategy_diversity(self, count: int) -> None:
        """Update strategy diversity metric.

        Args:
            count: Number of unique strategies
        """
        self.metrics.strategy_diversity = count
        self._save()

    def calculate_adaptation_speed(self) -> float:
        """Calculate how quickly agent adapts to new patterns.

        Returns:
            Adaptation speed (0.0 to 1.0)
        """
        if len(self.task_timeline) < 10:
            return 0.5  # Not enough data

        # Look at first 5 tasks vs last 5 tasks
        first_batch = list(self.task_timeline)[:5]
        last_batch = list(self.task_timeline)[-5:]

        first_success = sum(1 for t in first_batch if t["success"]) / 5.0
        last_success = sum(1 for t in last_batch if t["success"]) / 5.0

        # Adaptation speed is improvement from first to last
        adaptation = max(0.0, min(1.0, (last_success - first_success + 1.0) / 2.0))

        self.metrics.adaptation_speed = adaptation
        return adaptation

    def _default_metrics(self) -> LearningMetrics:
        """Create default metrics.

        Returns:
            Default LearningMetrics
        """
        return LearningMetrics(
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=0,
            avg_iterations=3.0,
            avg_duration=30.0,
            improvement_rate=0.0,
            adaptation_speed=0.5,
            memory_utilization=0.5,
            strategy_diversity=0,
            last_updated=time.time()
        )

    def _save(self) -> None:
        """Save meta-learning data to disk."""
        try:
            data = {
                "metrics": self.metrics.to_dict() if self.metrics else None,
                "task_timeline": list(self.task_timeline),
                "learning_events": self.learning_events,
                "saved_at": time.time()
            }

            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[MetaLearner] Error saving: {e}")

    def _load(self) -> None:
        """Load meta-learning data from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Restore metrics
            if data.get("metrics"):
                self.metrics = LearningMetrics.from_dict(data["metrics"])

            # Restore timeline
            self.task_timeline = deque(data.get("task_timeline", []), maxlen=100)

            # Restore events
            self.learning_events = data.get("learning_events", [])

            print(f"[MetaLearner] Loaded {self.metrics.total_tasks} tasks")
        except Exception as e:
            print(f"[MetaLearner] Error loading: {e}")
