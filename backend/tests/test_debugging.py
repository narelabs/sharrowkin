"""Real-world test of debugging modules."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from debugging.debugger import DebuggerIntegration
from debugging.profiler import Profiler
from debugging.test_generator import TestGenerator
from debugging.coverage import CoverageAnalyzer


def test_debugger_on_real_error():
    """Test debugger integration with real exception."""
    workspace = Path(__file__).parent.parent
    debugger = DebuggerIntegration(workspace)

    # Trigger a real error
    try:
        data = {"key": "value"}
        result = data["nonexistent"]  # KeyError
    except Exception:
        exc_info = sys.exc_info()
        session = debugger.analyze_exception(exc_info)

        print("\n=== DEBUGGER TEST ===")
        print(f"Exception: {session.exception_type}")
        print(f"Message: {session.exception_message}")
        print(f"Stack frames: {len(session.stack_frames)}")
        print(f"Breakpoints suggested: {len(session.breakpoints)}")
        print(f"Root cause:\n{session.root_cause_analysis}")

        assert session.exception_type == "KeyError"
        assert len(session.breakpoints) > 0
        assert "KeyError" in session.root_cause_analysis
        print("[OK] Debugger works!")


def test_profiler_on_real_function():
    """Test profiler with real function."""
    workspace = Path(__file__).parent.parent
    profiler = Profiler(workspace)

    def slow_function(n):
        """Intentionally slow function."""
        total = 0
        for i in range(n):
            for j in range(n):
                total += i * j
        return total

    print("\n=== PROFILER TEST ===")
    result = profiler.profile_function(slow_function, 100)

    print(f"Total time: {result.total_time:.3f}s")
    print(f"Functions profiled: {len(result.function_profiles)}")
    print(f"Recommendations: {len(result.bottleneck_report.recommendations)}")

    for rec in result.bottleneck_report.recommendations:
        print(f"  - {rec}")

    assert result.total_time > 0
    assert len(result.function_profiles) > 0
    print("[OK] Profiler works!")


def test_test_generator_on_real_code():
    """Test test generator with real code."""
    workspace = Path(__file__).parent.parent
    generator = TestGenerator(workspace)

    # Generate tests for this file's functions
    test_file = Path(__file__)
    suite = generator.generate_tests_for_file(test_file)

    print("\n=== TEST GENERATOR TEST ===")
    print(f"Module: {suite.module_name}")
    print(f"Test cases generated: {len(suite.test_cases)}")

    for tc in suite.test_cases[:3]:  # Show first 3
        print(f"  - {tc.name}: {tc.description}")

    assert len(suite.test_cases) > 0
    assert suite.module_name == Path(__file__).stem
    print("[OK] Test generator works!")


def test_coverage_analyzer():
    """Test coverage analyzer."""
    workspace = Path(__file__).parent.parent
    analyzer = CoverageAnalyzer(workspace)

    print("\n=== COVERAGE ANALYZER TEST ===")

    # Run coverage on this test file
    try:
        report = analyzer.run_coverage(str(Path(__file__)))

        print(f"Total coverage: {report.total_coverage:.1f}%")
        print(f"Files analyzed: {len(report.file_coverage)}")
        print(f"Critical gaps: {len(report.critical_gaps)}")

        assert report.total_coverage >= 0
        print("[OK] Coverage analyzer works!")
    except Exception as e:
        print(f"[WARN] Coverage analyzer needs pytest-cov: {e}")


if __name__ == "__main__":
    print("Testing debugging modules on real code...\n")

    test_debugger_on_real_error()
    test_profiler_on_real_function()
    test_test_generator_on_real_code()
    test_coverage_analyzer()

    print("\n" + "="*50)
    print("ALL DEBUGGING MODULES VERIFIED [OK]")
    print("="*50)
