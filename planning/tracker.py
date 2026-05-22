"""Progress tracking system for monitoring task execution.

This module provides real-time progress monitoring with metrics,
alerts for blockers, and visualization of execution progress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from .task_graph import Task, TaskGraph, TaskStatus


@dataclass
class ProgressMetrics:
    """Metrics for task execution progress."""

    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
    failed_tasks: int = 0
    blocked_tasks: int = 0

    # Time metrics
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: float = 0.0
    estimated_total_seconds: float = 0.0

    # Completion percentage
    completion_percentage: float = 0.0

    # Resource metrics
    active_workers: int = 0
    max_parallelism: int = 0

    # Velocity (tasks per hour)
    velocity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "in_progress_tasks": self.in_progress_tasks,
            "failed_tasks": self.failed_tasks,
            "blocked_tasks": self.blocked_tasks,
            "elapsed_seconds": self.elapsed_seconds,
            "estimated_remaining_seconds": self.estimated_remaining_seconds,
            "estimated_total_seconds": self.estimated_total_seconds,
            "completion_percentage": self.completion_percentage,
            "active_workers": self.active_workers,
            "max_parallelism": self.max_parallelism,
            "velocity": self.velocity,
        }


@dataclass
class ProgressAlert:
    """Alert for progress tracking issues."""

    severity: str  # "info", "warning", "error", "critical"
    message: str
    task_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        prefix = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }.get(self.severity, "•")

        task_info = f" [Task: {self.task_id}]" if self.task_id else ""
        return f"{prefix} {self.message}{task_info}"


class ProgressTracker:
    """Tracks progress of task execution with metrics and alerts."""

    def __init__(self, task_graph: TaskGraph) -> None:
        self.task_graph = task_graph
        self.start_time: datetime | None = None
        self.alerts: list[ProgressAlert] = []
        self.alert_callbacks: list[Callable[[ProgressAlert], None]] = []

        # Thresholds for alerts
        self.blocked_threshold_seconds = 300.0  # 5 minutes
        self.failure_rate_threshold = 0.3  # 30% failure rate
        self.velocity_drop_threshold = 0.5  # 50% velocity drop

        # Historical data for velocity calculation
        self.completion_history: list[tuple[datetime, int]] = []

    def start(self) -> None:
        """Start tracking progress."""
        self.start_time = datetime.now()
        self.completion_history = [(self.start_time, 0)]

    def get_metrics(self) -> ProgressMetrics:
        """Calculate current progress metrics."""
        metrics = ProgressMetrics()

        # Count tasks by status
        for task in self.task_graph.tasks.values():
            metrics.total_tasks += 1
            if task.status == TaskStatus.COMPLETED:
                metrics.completed_tasks += 1
            elif task.status == TaskStatus.IN_PROGRESS:
                metrics.in_progress_tasks += 1
            elif task.status == TaskStatus.FAILED:
                metrics.failed_tasks += 1
            elif task.status == TaskStatus.BLOCKED:
                metrics.blocked_tasks += 1

        # Calculate completion percentage
        if metrics.total_tasks > 0:
            metrics.completion_percentage = (metrics.completed_tasks / metrics.total_tasks) * 100

        # Calculate time metrics
        if self.start_time:
            metrics.elapsed_seconds = (datetime.now() - self.start_time).total_seconds()

        # Estimate remaining time based on completed tasks
        completed_with_duration = [
            t for t in self.task_graph.tasks.values()
            if t.status == TaskStatus.COMPLETED and t.actual_duration_seconds
        ]

        if completed_with_duration:
            avg_duration = sum(t.actual_duration_seconds or 0.0 for t in completed_with_duration) / len(completed_with_duration)
            remaining_tasks = metrics.total_tasks - metrics.completed_tasks
            metrics.estimated_remaining_seconds = avg_duration * remaining_tasks
            metrics.estimated_total_seconds = metrics.elapsed_seconds + metrics.estimated_remaining_seconds

        # Calculate parallelism
        metrics.active_workers = metrics.in_progress_tasks
        execution_order = self.task_graph.get_execution_order()
        metrics.max_parallelism = max(len(level) for level in execution_order) if execution_order else 0

        # Calculate velocity (tasks per hour)
        if metrics.elapsed_seconds > 0:
            hours = metrics.elapsed_seconds / 3600
            metrics.velocity = metrics.completed_tasks / hours if hours > 0 else 0.0

        return metrics

    def check_for_alerts(self) -> list[ProgressAlert]:
        """Check for issues and generate alerts."""
        new_alerts = []

        # Check for blocked tasks
        for task in self.task_graph.get_blocked_tasks():
            if task.started_at:
                blocked_duration = (datetime.now() - task.started_at).total_seconds()
                if blocked_duration > self.blocked_threshold_seconds:
                    alert = ProgressAlert(
                        severity="warning",
                        message=f"Task '{task.title}' has been blocked for {blocked_duration:.0f}s",
                        task_id=task.id,
                        metadata={"blocked_duration": blocked_duration},
                    )
                    new_alerts.append(alert)

        # Check for high failure rate
        metrics = self.get_metrics()
        if metrics.total_tasks > 0:
            failure_rate = metrics.failed_tasks / metrics.total_tasks
            if failure_rate > self.failure_rate_threshold:
                alert = ProgressAlert(
                    severity="error",
                    message=f"High failure rate: {failure_rate * 100:.1f}% of tasks failed",
                    metadata={"failure_rate": failure_rate},
                )
                new_alerts.append(alert)

        # Check for velocity drop
        if len(self.completion_history) > 1:
            recent_velocity = self._calculate_recent_velocity()
            overall_velocity = metrics.velocity
            if overall_velocity > 0 and recent_velocity < overall_velocity * self.velocity_drop_threshold:
                alert = ProgressAlert(
                    severity="warning",
                    message=f"Velocity dropped: {recent_velocity:.2f} tasks/hour (was {overall_velocity:.2f})",
                    metadata={"recent_velocity": recent_velocity, "overall_velocity": overall_velocity},
                )
                new_alerts.append(alert)

        # Check for tasks exceeding estimated duration
        for task in self.task_graph.tasks.values():
            if task.status == TaskStatus.IN_PROGRESS and task.estimated_duration_seconds and task.started_at:
                elapsed = (datetime.now() - task.started_at).total_seconds()
                if elapsed > task.estimated_duration_seconds * 1.5:  # 50% over estimate
                    alert = ProgressAlert(
                        severity="info",
                        message=f"Task '{task.title}' is taking longer than estimated",
                        task_id=task.id,
                        metadata={
                            "estimated": task.estimated_duration_seconds,
                            "actual": elapsed,
                        },
                    )
                    new_alerts.append(alert)

        # Store and trigger callbacks
        for alert in new_alerts:
            self.alerts.append(alert)
            for callback in self.alert_callbacks:
                callback(alert)

        return new_alerts

    def _calculate_recent_velocity(self, window_minutes: int = 10) -> float:
        """Calculate velocity over recent time window."""
        if not self.completion_history:
            return 0.0

        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        recent_completions = [
            (ts, count) for ts, count in self.completion_history
            if ts >= cutoff_time
        ]

        if len(recent_completions) < 2:
            return 0.0

        first_ts, first_count = recent_completions[0]
        last_ts, last_count = recent_completions[-1]

        time_diff_hours = (last_ts - first_ts).total_seconds() / 3600
        if time_diff_hours == 0:
            return 0.0

        return (last_count - first_count) / time_diff_hours

    def on_task_completed(self, task_id: str) -> None:
        """Callback when a task is completed."""
        metrics = self.get_metrics()
        self.completion_history.append((datetime.now(), metrics.completed_tasks))

        # Keep only recent history (last hour)
        cutoff = datetime.now() - timedelta(hours=1)
        self.completion_history = [
            (ts, count) for ts, count in self.completion_history
            if ts >= cutoff
        ]

    def add_alert_callback(self, callback: Callable[[ProgressAlert], None]) -> None:
        """Register a callback for alerts."""
        self.alert_callbacks.append(callback)

    def get_progress_summary(self) -> str:
        """Generate a human-readable progress summary."""
        metrics = self.get_metrics()
        lines = [
            "Progress Summary",
            "=" * 50,
            f"Completed: {metrics.completed_tasks}/{metrics.total_tasks} ({metrics.completion_percentage:.1f}%)",
            f"In Progress: {metrics.in_progress_tasks}",
            f"Failed: {metrics.failed_tasks}",
            f"Blocked: {metrics.blocked_tasks}",
            "",
            f"Elapsed Time: {self._format_duration(metrics.elapsed_seconds)}",
        ]

        if metrics.estimated_remaining_seconds > 0:
            lines.append(f"Estimated Remaining: {self._format_duration(metrics.estimated_remaining_seconds)}")
            lines.append(f"Estimated Total: {self._format_duration(metrics.estimated_total_seconds)}")

        if metrics.velocity > 0:
            lines.append(f"Velocity: {metrics.velocity:.2f} tasks/hour")

        lines.append(f"Max Parallelism: {metrics.max_parallelism}")

        # Add recent alerts
        if self.alerts:
            lines.append("")
            lines.append("Recent Alerts:")
            for alert in self.alerts[-5:]:  # Last 5 alerts
                lines.append(f"  {alert}")

        return "\n".join(lines)

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    def get_progress_bar(self, width: int = 40) -> str:
        """Generate a text progress bar."""
        metrics = self.get_metrics()
        filled = int(width * metrics.completion_percentage / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {metrics.completion_percentage:.1f}%"
