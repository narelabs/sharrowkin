"""Debugging subsystem for Sharrowkin agent.

Provides intelligent debugging capabilities:
- Debugger integration (pdb/ipdb)
- Profiling (cProfile, py-spy)
- Test generation
- Coverage analysis
"""

from .debugger import DebuggerIntegration, BreakpointStrategy
from .profiler import Profiler, ProfileResult, BottleneckReport
from .test_generator import TestGenerator, TestCase, TestSuite
from .coverage import CoverageAnalyzer, CoverageReport

__all__ = [
    "DebuggerIntegration",
    "BreakpointStrategy",
    "Profiler",
    "ProfileResult",
    "BottleneckReport",
    "TestGenerator",
    "TestCase",
    "TestSuite",
    "CoverageAnalyzer",
    "CoverageReport",
]
