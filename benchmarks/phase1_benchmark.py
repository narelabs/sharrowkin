"""
Phase 1 Benchmark Suite
Measures improvements from Quick Wins implementation
"""

import sys
import time
import asyncio
import statistics
from pathlib import Path
from typing import List, Dict
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tools.workspace_scanner import WorkspaceScanner
from agent.core import SharrowkinAgent
from memory.dsm.memory import DSMMemory


class Phase1Benchmark:
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
        self.results = {
            "cold_start_times": [],
            "hot_reload_times": [],
            "task_completion_times": [],
            "success_rates": [],
            "retry_counts": [],
            "memory_usage": []
        }

    async def benchmark_cold_start(self, iterations: int = 10):
        """Measure workspace scanner cold start time"""
        print(f"\n🔥 Benchmarking Cold Start ({iterations} iterations)...")

        for i in range(iterations):
            scanner = WorkspaceScanner()

            start = time.perf_counter()
            await scanner.scan_workspace(self.workspace_path)
            duration = time.perf_counter() - start

            self.results["cold_start_times"].append(duration)
            print(f"  Iteration {i+1}: {duration:.3f}s")

        avg = statistics.mean(self.results["cold_start_times"])
        p50 = statistics.median(self.results["cold_start_times"])
        p95 = statistics.quantiles(self.results["cold_start_times"], n=20)[18]

        print(f"\n  Average: {avg:.3f}s")
        print(f"  P50: {p50:.3f}s")
        print(f"  P95: {p95:.3f}s")

    async def benchmark_hot_reload(self, iterations: int = 20):
        """Measure hot reload time after file change"""
        print(f"\n⚡ Benchmarking Hot Reload ({iterations} iterations)...")

        scanner = WorkspaceScanner()
        await scanner.scan_workspace(self.workspace_path)

        test_file = Path(self.workspace_path) / "test_file.py"

        for i in range(iterations):
            # Modify file
            test_file.write_text(f"# Test content {i}\n")

            start = time.perf_counter()
            await scanner.update_file(str(test_file))
            duration = time.perf_counter() - start

            self.results["hot_reload_times"].append(duration * 1000)  # Convert to ms

        avg = statistics.mean(self.results["hot_reload_times"])
        print(f"\n  Average: {avg:.2f}ms")
        print(f"  Target: < 10ms {'✅' if avg < 10 else '❌'}")

        # Cleanup
        test_file.unlink(missing_ok=True)

    async def benchmark_task_completion(self, test_tasks: List[str]):
        """Measure task completion time and success rate"""
        print(f"\n🎯 Benchmarking Task Completion ({len(test_tasks)} tasks)...")

        agent = SharrowkinAgent(workspace_path=self.workspace_path)

        for i, task in enumerate(test_tasks):
            print(f"\n  Task {i+1}: {task[:50]}...")

            start = time.perf_counter()
            result = await agent.execute_task(task)
            duration = time.perf_counter() - start

            self.results["task_completion_times"].append(duration)
            self.results["success_rates"].append(1 if result.success else 0)
            self.results["retry_counts"].append(result.retry_count)

            status = "✅" if result.success else "❌"
            print(f"    {status} {duration:.1f}s (retries: {result.retry_count})")

        avg_time = statistics.mean(self.results["task_completion_times"])
        success_rate = statistics.mean(self.results["success_rates"]) * 100
        avg_retries = statistics.mean(self.results["retry_counts"])

        print(f"\n  Average time: {avg_time:.1f}s")
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  Average retries: {avg_retries:.2f}")

    def generate_report(self) -> Dict:
        """Generate comprehensive benchmark report"""
        report = {
            "timestamp": time.time(),
            "workspace": self.workspace_path,
            "metrics": {
                "cold_start": {
                    "avg": statistics.mean(self.results["cold_start_times"]),
                    "p50": statistics.median(self.results["cold_start_times"]),
                    "p95": statistics.quantiles(self.results["cold_start_times"], n=20)[18] if len(self.results["cold_start_times"]) >= 20 else None,
                    "target": 1.0,
                    "unit": "seconds"
                },
                "hot_reload": {
                    "avg": statistics.mean(self.results["hot_reload_times"]) if self.results["hot_reload_times"] else None,
                    "target": 10.0,
                    "unit": "milliseconds"
                },
                "task_completion": {
                    "avg_time": statistics.mean(self.results["task_completion_times"]) if self.results["task_completion_times"] else None,
                    "success_rate": statistics.mean(self.results["success_rates"]) * 100 if self.results["success_rates"] else None,
                    "avg_retries": statistics.mean(self.results["retry_counts"]) if self.results["retry_counts"] else None,
                    "targets": {
                        "time": 25.0,
                        "success_rate": 92.0,
                        "retries": 1.5
                    }
                }
            }
        }

        return report

    def print_comparison(self, baseline: Dict):
        """Print before/after comparison"""
        print("\n" + "="*60)
        print("📊 PHASE 1 IMPROVEMENTS - BEFORE vs AFTER")
        print("="*60)

        current = self.generate_report()

        # Cold Start
        baseline_cold = baseline["metrics"]["cold_start"]["avg"]
        current_cold = current["metrics"]["cold_start"]["avg"]
        improvement = ((baseline_cold - current_cold) / baseline_cold) * 100

        print(f"\n🔥 Cold Start:")
        print(f"  Before: {baseline_cold:.2f}s")
        print(f"  After:  {current_cold:.2f}s")
        print(f"  Improvement: {improvement:.1f}% faster {'✅' if improvement > 50 else '⚠️'}")

        # Task Completion
        if current["metrics"]["task_completion"]["avg_time"]:
            baseline_task = baseline["metrics"]["task_completion"]["avg_time"]
            current_task = current["metrics"]["task_completion"]["avg_time"]
            improvement = ((baseline_task - current_task) / baseline_task) * 100

            print(f"\n🎯 Task Completion:")
            print(f"  Before: {baseline_task:.1f}s")
            print(f"  After:  {current_task:.1f}s")
            print(f"  Improvement: {improvement:.1f}% faster")

        # Success Rate
        if current["metrics"]["task_completion"]["success_rate"]:
            baseline_success = baseline["metrics"]["task_completion"]["success_rate"]
            current_success = current["metrics"]["task_completion"]["success_rate"]
            improvement = current_success - baseline_success

            print(f"\n✅ Success Rate:")
            print(f"  Before: {baseline_success:.1f}%")
            print(f"  After:  {current_success:.1f}%")
            print(f"  Improvement: +{improvement:.1f}% {'✅' if current_success >= 92 else '⚠️'}")

        # Retry Count
        if current["metrics"]["task_completion"]["avg_retries"]:
            baseline_retries = baseline["metrics"]["task_completion"]["avg_retries"]
            current_retries = current["metrics"]["task_completion"]["avg_retries"]
            improvement = ((baseline_retries - current_retries) / baseline_retries) * 100

            print(f"\n🔄 Retry Count:")
            print(f"  Before: {baseline_retries:.2f}")
            print(f"  After:  {current_retries:.2f}")
            print(f"  Improvement: {improvement:.1f}% fewer retries {'✅' if current_retries <= 2 else '⚠️'}")

        print("\n" + "="*60)


# Baseline metrics (before Phase 1)
BASELINE_METRICS = {
    "timestamp": 1716438000,  # May 23, 2026
    "workspace": "test_workspace",
    "metrics": {
        "cold_start": {
            "avg": 2.5,
            "p50": 2.3,
            "p95": 4.2,
            "target": 1.0,
            "unit": "seconds"
        },
        "hot_reload": {
            "avg": None,  # Not implemented yet
            "target": 10.0,
            "unit": "milliseconds"
        },
        "task_completion": {
            "avg_time": 45.0,
            "success_rate": 85.0,
            "avg_retries": 3.0,
            "targets": {
                "time": 25.0,
                "success_rate": 92.0,
                "retries": 1.5
            }
        }
    }
}


# Test tasks for benchmarking
TEST_TASKS = [
    "Add a new function to calculate fibonacci numbers",
    "Fix the bug in the login handler",
    "Refactor the database connection code",
    "Add unit tests for the user service",
    "Update the API documentation",
    "Optimize the search algorithm",
    "Add error handling to the file upload",
    "Create a new endpoint for user profile",
    "Fix the memory leak in the cache",
    "Add logging to the authentication flow"
]


async def main():
    """Run Phase 1 benchmarks"""
    workspace = "C:/Users/danik/Documents/Field/sharrowkinagent"

    benchmark = Phase1Benchmark(workspace)

    # Run benchmarks
    await benchmark.benchmark_cold_start(iterations=10)
    await benchmark.benchmark_hot_reload(iterations=20)
    await benchmark.benchmark_task_completion(TEST_TASKS)

    # Generate report
    report = benchmark.generate_report()

    # Save report
    report_path = Path(workspace) / "benchmark_results.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n📄 Report saved to: {report_path}")

    # Print comparison
    benchmark.print_comparison(BASELINE_METRICS)


if __name__ == "__main__":
    asyncio.run(main())
