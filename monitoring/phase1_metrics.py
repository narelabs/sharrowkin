"""
Phase 1 Metrics Monitoring
Real-time tracking of improvements
"""

import time
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from collections import deque
import statistics
import json
from pathlib import Path


@dataclass
class MetricSnapshot:
    """Single metric measurement"""
    timestamp: float
    metric_name: str
    value: float
    metadata: Optional[Dict] = None


class Phase1Metrics:
    """Track Phase 1 improvement metrics in real-time"""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size

        # Rolling windows for metrics
        self.cold_start_times = deque(maxlen=window_size)
        self.hot_reload_times = deque(maxlen=window_size)
        self.task_completion_times = deque(maxlen=window_size)
        self.success_flags = deque(maxlen=window_size)
        self.retry_counts = deque(maxlen=window_size)

        # Targets from roadmap
        self.targets = {
            "cold_start": 1.0,  # seconds
            "hot_reload": 10.0,  # milliseconds
            "task_completion": 25.0,  # seconds
            "success_rate": 92.0,  # percentage
            "avg_retries": 1.5
        }

    def record_cold_start(self, duration: float):
        """Record workspace scanner cold start time"""
        self.cold_start_times.append(duration)

    def record_hot_reload(self, duration_ms: float):
        """Record file watcher hot reload time"""
        self.hot_reload_times.append(duration_ms)

    def record_task_completion(self, duration: float, success: bool, retries: int):
        """Record task execution metrics"""
        self.task_completion_times.append(duration)
        self.success_flags.append(1 if success else 0)
        self.retry_counts.append(retries)

    def get_cold_start_stats(self) -> Dict:
        """Get cold start statistics"""
        if not self.cold_start_times:
            return {"status": "no_data"}

        times = list(self.cold_start_times)
        return {
            "avg": statistics.mean(times),
            "p50": statistics.median(times),
            "p95": statistics.quantiles(times, n=20)[18] if len(times) >= 20 else None,
            "min": min(times),
            "max": max(times),
            "target": self.targets["cold_start"],
            "meets_target": statistics.mean(times) <= self.targets["cold_start"],
            "sample_size": len(times)
        }

    def get_hot_reload_stats(self) -> Dict:
        """Get hot reload statistics"""
        if not self.hot_reload_times:
            return {"status": "no_data"}

        times = list(self.hot_reload_times)
        return {
            "avg": statistics.mean(times),
            "p50": statistics.median(times),
            "p95": statistics.quantiles(times, n=20)[18] if len(times) >= 20 else None,
            "min": min(times),
            "max": max(times),
            "target": self.targets["hot_reload"],
            "meets_target": statistics.mean(times) <= self.targets["hot_reload"],
            "sample_size": len(times)
        }

    def get_task_completion_stats(self) -> Dict:
        """Get task completion statistics"""
        if not self.task_completion_times:
            return {"status": "no_data"}

        times = list(self.task_completion_times)
        success_rate = statistics.mean(self.success_flags) * 100
        avg_retries = statistics.mean(self.retry_counts)

        return {
            "avg_time": statistics.mean(times),
            "p50_time": statistics.median(times),
            "success_rate": success_rate,
            "avg_retries": avg_retries,
            "targets": {
                "time": self.targets["task_completion"],
                "success_rate": self.targets["success_rate"],
                "retries": self.targets["avg_retries"]
            },
            "meets_targets": {
                "time": statistics.mean(times) <= self.targets["task_completion"],
                "success_rate": success_rate >= self.targets["success_rate"],
                "retries": avg_retries <= self.targets["avg_retries"]
            },
            "sample_size": len(times)
        }

    def get_overall_health(self) -> Dict:
        """Get overall Phase 1 health status"""
        cold_start = self.get_cold_start_stats()
        hot_reload = self.get_hot_reload_stats()
        task_completion = self.get_task_completion_stats()

        # Calculate health score (0-100)
        health_score = 0
        checks = 0

        if cold_start.get("meets_target"):
            health_score += 25
        checks += 1

        if hot_reload.get("meets_target"):
            health_score += 25
        checks += 1

        if task_completion.get("meets_targets", {}).get("success_rate"):
            health_score += 25
        checks += 1

        if task_completion.get("meets_targets", {}).get("retries"):
            health_score += 25
        checks += 1

        return {
            "health_score": health_score,
            "status": self._get_health_status(health_score),
            "checks_passed": sum([
                cold_start.get("meets_target", False),
                hot_reload.get("meets_target", False),
                task_completion.get("meets_targets", {}).get("success_rate", False),
                task_completion.get("meets_targets", {}).get("retries", False)
            ]),
            "total_checks": checks,
            "cold_start": cold_start,
            "hot_reload": hot_reload,
            "task_completion": task_completion
        }

    def _get_health_status(self, score: int) -> str:
        """Convert health score to status"""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 50:
            return "fair"
        else:
            return "needs_improvement"

    def export_report(self, filepath: str):
        """Export metrics report to JSON"""
        report = {
            "timestamp": time.time(),
            "phase": "Phase 1 - Quick Wins",
            "metrics": self.get_overall_health()
        }

        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)

    def print_dashboard(self):
        """Print real-time metrics dashboard"""
        health = self.get_overall_health()

        print("\n" + "="*70)
        print("📊 PHASE 1 METRICS DASHBOARD")
        print("="*70)

        # Health Score
        status_emoji = {
            "excellent": "🟢",
            "good": "🟡",
            "fair": "🟠",
            "needs_improvement": "🔴"
        }
        emoji = status_emoji.get(health["status"], "⚪")

        print(f"\n{emoji} Overall Health: {health['health_score']}/100 ({health['status'].upper()})")
        print(f"   Checks Passed: {health['checks_passed']}/{health['total_checks']}")

        # Cold Start
        cold_start = health["cold_start"]
        if cold_start.get("avg"):
            target_met = "✅" if cold_start["meets_target"] else "❌"
            print(f"\n🔥 Cold Start: {cold_start['avg']:.2f}s (target: {cold_start['target']}s) {target_met}")
            print(f"   P50: {cold_start['p50']:.2f}s | P95: {cold_start.get('p95', 'N/A')}")
            print(f"   Range: {cold_start['min']:.2f}s - {cold_start['max']:.2f}s")

        # Hot Reload
        hot_reload = health["hot_reload"]
        if hot_reload.get("avg"):
            target_met = "✅" if hot_reload["meets_target"] else "❌"
            print(f"\n⚡ Hot Reload: {hot_reload['avg']:.2f}ms (target: {hot_reload['target']}ms) {target_met}")
            print(f"   P50: {hot_reload['p50']:.2f}ms | P95: {hot_reload.get('p95', 'N/A')}")

        # Task Completion
        task = health["task_completion"]
        if task.get("avg_time"):
            time_met = "✅" if task["meets_targets"]["time"] else "❌"
            success_met = "✅" if task["meets_targets"]["success_rate"] else "❌"
            retry_met = "✅" if task["meets_targets"]["retries"] else "❌"

            print(f"\n🎯 Task Completion:")
            print(f"   Time: {task['avg_time']:.1f}s (target: {task['targets']['time']}s) {time_met}")
            print(f"   Success Rate: {task['success_rate']:.1f}% (target: {task['targets']['success_rate']}%) {success_met}")
            print(f"   Avg Retries: {task['avg_retries']:.2f} (target: {task['targets']['retries']}) {retry_met}")

        print("\n" + "="*70)


class MetricsCollector:
    """Background metrics collector"""

    def __init__(self, metrics: Phase1Metrics, export_interval: int = 60):
        self.metrics = metrics
        self.export_interval = export_interval
        self.running = False
        self.export_path = Path("metrics_reports")
        self.export_path.mkdir(exist_ok=True)

    async def start(self):
        """Start background collection"""
        self.running = True
        asyncio.create_task(self._export_loop())

    async def stop(self):
        """Stop background collection"""
        self.running = False

    async def _export_loop(self):
        """Periodically export metrics"""
        while self.running:
            await asyncio.sleep(self.export_interval)

            timestamp = int(time.time())
            filepath = self.export_path / f"metrics_{timestamp}.json"

            self.metrics.export_report(str(filepath))
            print(f"📊 Metrics exported to {filepath}")


# Global metrics instance
_metrics_instance: Optional[Phase1Metrics] = None


def get_metrics() -> Phase1Metrics:
    """Get global metrics instance"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = Phase1Metrics()
    return _metrics_instance


# Convenience functions for recording metrics
def record_cold_start(duration: float):
    get_metrics().record_cold_start(duration)


def record_hot_reload(duration_ms: float):
    get_metrics().record_hot_reload(duration_ms)


def record_task_completion(duration: float, success: bool, retries: int):
    get_metrics().record_task_completion(duration, success, retries)


def print_dashboard():
    get_metrics().print_dashboard()


def export_report(filepath: str):
    get_metrics().export_report(filepath)


# Example usage
if __name__ == "__main__":
    metrics = Phase1Metrics()

    # Simulate some metrics
    print("Simulating Phase 1 metrics...\n")

    # Cold starts (improving over time)
    for i in range(20):
        metrics.record_cold_start(2.5 - (i * 0.1))  # 2.5s → 0.5s

    # Hot reloads
    for i in range(30):
        metrics.record_hot_reload(15 - (i * 0.3))  # 15ms → 6ms

    # Task completions
    for i in range(50):
        duration = 45 - (i * 0.4)  # 45s → 25s
        success = i > 5  # First 5 fail, rest succeed
        retries = max(1, 3 - (i // 10))  # 3 → 1 retries

        metrics.record_task_completion(duration, success, retries)

    # Print dashboard
    metrics.print_dashboard()

    # Export report
    metrics.export_report("phase1_metrics_example.json")
    print("\n✅ Example report exported to phase1_metrics_example.json")
