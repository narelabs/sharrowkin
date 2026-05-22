"""Profiler for performance analysis.

Integrates with cProfile and py-spy for:
- Performance profiling
- Bottleneck identification
- Optimization recommendations
"""

import cProfile
import pstats
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass
class FunctionProfile:
    """Profile data for a single function."""
    name: str
    file_path: str
    line_number: int
    calls: int
    total_time: float
    cumulative_time: float
    time_per_call: float


@dataclass
class BottleneckReport:
    """Report of performance bottlenecks."""
    top_time_consumers: List[FunctionProfile]
    top_call_counts: List[FunctionProfile]
    recommendations: List[str]
    total_time: float


@dataclass
class ProfileResult:
    """Result of profiling run."""
    total_time: float
    function_profiles: List[FunctionProfile]
    bottleneck_report: BottleneckReport
    stats_file: Optional[Path]


class Profiler:
    """Performance profiler with bottleneck detection."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    def profile_function(self, func: Callable, *args, **kwargs) -> ProfileResult:
        """Profile a function execution.
        
        Args:
            func: Function to profile
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            ProfileResult with performance data
        """
        profiler = cProfile.Profile()
        
        start_time = time.time()
        profiler.enable()
        
        try:
            result = func(*args, **kwargs)
        finally:
            profiler.disable()
        
        total_time = time.time() - start_time
        
        # Extract stats
        stats = pstats.Stats(profiler)
        function_profiles = self._extract_function_profiles(stats)
        
        # Generate bottleneck report
        bottleneck_report = self._analyze_bottlenecks(function_profiles, total_time)
        
        return ProfileResult(
            total_time=total_time,
            function_profiles=function_profiles,
            bottleneck_report=bottleneck_report,
            stats_file=None,
        )

    def profile_script(self, script_path: Path, output_path: Optional[Path] = None) -> ProfileResult:
        """Profile a Python script.
        
        Args:
            script_path: Path to script to profile
            output_path: Optional path to save stats
            
        Returns:
            ProfileResult with performance data
        """
        if output_path is None:
            output_path = self.workspace_path / ".sharrowkin" / "profile_stats.prof"
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Run cProfile
        cmd = [
            "python", "-m", "cProfile",
            "-o", str(output_path),
            str(script_path),
        ]
        
        start_time = time.time()
        subprocess.run(cmd, check=True)
        total_time = time.time() - start_time
        
        # Load stats
        stats = pstats.Stats(str(output_path))
        function_profiles = self._extract_function_profiles(stats)
        
        # Generate bottleneck report
        bottleneck_report = self._analyze_bottlenecks(function_profiles, total_time)
        
        return ProfileResult(
            total_time=total_time,
            function_profiles=function_profiles,
            bottleneck_report=bottleneck_report,
            stats_file=output_path,
        )

    def _extract_function_profiles(self, stats: pstats.Stats) -> List[FunctionProfile]:
        """Extract function profiles from stats."""
        profiles = []
        
        for func_key, (cc, nc, tt, ct, callers) in stats.stats.items():
            file_path, line_number, func_name = func_key
            
            # Only include workspace files
            if not self._is_workspace_file(Path(file_path)):
                continue
            
            profiles.append(FunctionProfile(
                name=func_name,
                file_path=file_path,
                line_number=line_number,
                calls=nc,
                total_time=tt,
                cumulative_time=ct,
                time_per_call=tt / nc if nc > 0 else 0,
            ))
        
        return profiles

    def _analyze_bottlenecks(self, profiles: List[FunctionProfile], total_time: float) -> BottleneckReport:
        """Analyze bottlenecks and generate recommendations."""
        # Sort by total time
        by_time = sorted(profiles, key=lambda p: p.total_time, reverse=True)[:10]
        
        # Sort by call count
        by_calls = sorted(profiles, key=lambda p: p.calls, reverse=True)[:10]
        
        # Generate recommendations
        recommendations = []
        
        # Check for time-consuming functions
        if by_time:
            top_func = by_time[0]
            if top_func.total_time > total_time * 0.3:
                recommendations.append(
                    f"Function '{top_func.name}' consumes {top_func.total_time/total_time*100:.1f}% of total time. "
                    f"Consider optimizing this function."
                )
        
        # Check for frequently called functions
        if by_calls:
            top_func = by_calls[0]
            if top_func.calls > 1000:
                recommendations.append(
                    f"Function '{top_func.name}' is called {top_func.calls} times. "
                    f"Consider caching or reducing call frequency."
                )
        
        # Check for slow per-call functions
        slow_funcs = [p for p in profiles if p.time_per_call > 0.1 and p.calls > 10]
        if slow_funcs:
            func = slow_funcs[0]
            recommendations.append(
                f"Function '{func.name}' takes {func.time_per_call:.3f}s per call. "
                f"Consider optimizing algorithm or using faster data structures."
            )
        
        # General recommendations
        if not recommendations:
            recommendations.append("No major bottlenecks detected. Profile looks good!")
        
        return BottleneckReport(
            top_time_consumers=by_time,
            top_call_counts=by_calls,
            recommendations=recommendations,
            total_time=total_time,
        )

    def _is_workspace_file(self, file_path: Path) -> bool:
        """Check if file is in workspace."""
        try:
            file_path.relative_to(self.workspace_path)
            return True
        except (ValueError, OSError):
            return False

    def format_report(self, result: ProfileResult) -> str:
        """Format profile result as readable report."""
        lines = [
            "=" * 80,
            "PERFORMANCE PROFILE REPORT",
            "=" * 80,
            f"Total execution time: {result.total_time:.3f}s",
            "",
            "TOP 10 TIME CONSUMERS:",
            "-" * 80,
        ]
        
        for i, func in enumerate(result.bottleneck_report.top_time_consumers, 1):
            pct = func.total_time / result.total_time * 100
            lines.append(
                f"{i:2d}. {func.name:40s} {func.total_time:8.3f}s ({pct:5.1f}%) "
                f"[{func.calls:6d} calls]"
            )
        
        lines.extend([
            "",
            "TOP 10 MOST CALLED:",
            "-" * 80,
        ])
        
        for i, func in enumerate(result.bottleneck_report.top_call_counts, 1):
            lines.append(
                f"{i:2d}. {func.name:40s} {func.calls:8d} calls "
                f"[{func.time_per_call*1000:6.2f}ms/call]"
            )
        
        lines.extend([
            "",
            "RECOMMENDATIONS:",
            "-" * 80,
        ])
        
        for i, rec in enumerate(result.bottleneck_report.recommendations, 1):
            lines.append(f"{i}. {rec}")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)
