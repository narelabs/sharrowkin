"""Code coverage analysis for test quality assessment.

Analyzes test coverage and identifies untested code paths.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileCoverage:
    """Coverage data for a single file."""

    file_path: str
    total_lines: int
    covered_lines: int
    missing_lines: list[int] = field(default_factory=list)
    coverage_percent: float = 0.0
    branches_total: int = 0
    branches_covered: int = 0


@dataclass
class FunctionCoverage:
    """Coverage data for a single function."""

    name: str
    file_path: str
    line_number: int
    covered: bool
    coverage_percent: float = 0.0


@dataclass
class CoverageReport:
    """Complete coverage analysis report."""

    total_coverage: float
    line_coverage: float
    branch_coverage: float
    files: list[FileCoverage] = field(default_factory=list)
    functions: list[FunctionCoverage] = field(default_factory=list)
    untested_files: list[str] = field(default_factory=list)
    untested_functions: list[FunctionCoverage] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class CoverageAnalyzer:
    """Analyzes code coverage from test runs."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def run_coverage(self, test_path: str | None = None) -> CoverageReport:
        """Run pytest with coverage and analyze results."""
        try:
            # Run pytest with coverage
            cmd = ["pytest", "--cov=.", "--cov-report=json", "--cov-report=term"]
            if test_path:
                cmd.append(test_path)

            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=300,
            )

            # Parse coverage data
            coverage_file = self.workspace / ".coverage"
            if coverage_file.exists():
                return self._parse_coverage_data()
            else:
                return self._create_empty_report()

        except subprocess.TimeoutExpired:
            print("Coverage analysis timed out")
            return self._create_empty_report()
        except Exception as e:
            print(f"Error running coverage: {e}")
            return self._create_empty_report()

    def _parse_coverage_data(self) -> CoverageReport:
        """Parse coverage data from .coverage file."""
        import json

        coverage_json = self.workspace / "coverage.json"

        if not coverage_json.exists():
            return self._create_empty_report()

        try:
            with open(coverage_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            files = []
            total_lines = 0
            covered_lines = 0

            for file_path, file_data in data.get("files", {}).items():
                summary = file_data.get("summary", {})

                file_cov = FileCoverage(
                    file_path=file_path,
                    total_lines=summary.get("num_statements", 0),
                    covered_lines=summary.get("covered_lines", 0),
                    missing_lines=file_data.get("missing_lines", []),
                    coverage_percent=summary.get("percent_covered", 0.0),
                    branches_total=summary.get("num_branches", 0),
                    branches_covered=summary.get("covered_branches", 0),
                )

                files.append(file_cov)
                total_lines += file_cov.total_lines
                covered_lines += file_cov.covered_lines

            # Calculate overall coverage
            total_coverage = (
                (covered_lines / total_lines * 100) if total_lines > 0 else 0.0
            )

            # Identify untested files
            untested_files = [f.file_path for f in files if f.coverage_percent < 10.0]

            # Analyze functions
            functions = self._analyze_function_coverage(files)
            untested_functions = [f for f in functions if not f.covered]

            # Generate recommendations
            recommendations = self._generate_recommendations(
                total_coverage, untested_files, untested_functions
            )

            return CoverageReport(
                total_coverage=total_coverage,
                line_coverage=total_coverage,
                branch_coverage=data.get("totals", {}).get("percent_covered_display", 0.0),
                files=files,
                functions=functions,
                untested_files=untested_files,
                untested_functions=untested_functions,
                recommendations=recommendations,
            )

        except Exception as e:
            print(f"Error parsing coverage data: {e}")
            return self._create_empty_report()

    def _analyze_function_coverage(self, files: list[FileCoverage]) -> list[FunctionCoverage]:
        """Analyze coverage at function level."""
        functions = []

        for file_cov in files:
            try:
                file_path = Path(file_cov.file_path)
                if not file_path.exists():
                    continue

                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Check if function lines are covered
                        func_lines = range(node.lineno, (node.end_lineno or node.lineno) + 1)
                        missing_in_func = [
                            line for line in file_cov.missing_lines if line in func_lines
                        ]

                        covered = len(missing_in_func) == 0
                        coverage_percent = (
                            (len(func_lines) - len(missing_in_func)) / len(func_lines) * 100
                            if len(func_lines) > 0
                            else 0.0
                        )

                        func_cov = FunctionCoverage(
                            name=node.name,
                            file_path=file_cov.file_path,
                            line_number=node.lineno,
                            covered=covered,
                            coverage_percent=coverage_percent,
                        )
                        functions.append(func_cov)

            except Exception as e:
                print(f"Error analyzing functions in {file_cov.file_path}: {e}")

        return functions

    def _generate_recommendations(
        self,
        total_coverage: float,
        untested_files: list[str],
        untested_functions: list[FunctionCoverage],
    ) -> list[str]:
        """Generate recommendations for improving coverage."""
        recommendations = []

        if total_coverage < 50:
            recommendations.append(
                f"⚠️ Coverage is low ({total_coverage:.1f}%). "
                "Aim for at least 80% coverage for production code."
            )
        elif total_coverage < 80:
            recommendations.append(
                f"Coverage is moderate ({total_coverage:.1f}%). "
                "Consider adding more tests to reach 80%+ coverage."
            )
        else:
            recommendations.append(
                f"✓ Good coverage ({total_coverage:.1f}%). "
                "Focus on edge cases and error handling."
            )

        if untested_files:
            recommendations.append(
                f"Add tests for {len(untested_files)} untested files: "
                f"{', '.join(untested_files[:3])}"
                + ("..." if len(untested_files) > 3 else "")
            )

        if untested_functions:
            top_untested = untested_functions[:5]
            recommendations.append(
                f"Add tests for {len(untested_functions)} untested functions, starting with: "
                f"{', '.join(f.name for f in top_untested)}"
            )

        # Specific recommendations
        if any("__init__" in f for f in untested_files):
            recommendations.append(
                "Consider adding integration tests for module initialization"
            )

        if any("error" in f.lower() or "exception" in f.lower() for f in untested_files):
            recommendations.append(
                "Add tests for error handling and exception paths"
            )

        return recommendations

    def _create_empty_report(self) -> CoverageReport:
        """Create empty coverage report."""
        return CoverageReport(
            total_coverage=0.0,
            line_coverage=0.0,
            branch_coverage=0.0,
            recommendations=["Unable to generate coverage report. Ensure pytest-cov is installed."],
        )

    def identify_critical_gaps(self, report: CoverageReport) -> list[str]:
        """Identify critical gaps in test coverage."""
        gaps = []

        # Files with 0% coverage
        zero_coverage = [f for f in report.files if f.coverage_percent == 0]
        if zero_coverage:
            gaps.append(
                f"Critical: {len(zero_coverage)} files have 0% coverage: "
                f"{', '.join(f.file_path for f in zero_coverage[:3])}"
            )

        # Public API functions without tests
        public_untested = [
            f for f in report.untested_functions if not f.name.startswith("_")
        ]
        if public_untested:
            gaps.append(
                f"Critical: {len(public_untested)} public functions untested: "
                f"{', '.join(f.name for f in public_untested[:5])}"
            )

        # Low branch coverage
        if report.branch_coverage < 50:
            gaps.append(
                f"Critical: Branch coverage is only {report.branch_coverage:.1f}%. "
                "Many code paths are untested."
            )

        return gaps

    def format_report(self, report: CoverageReport) -> str:
        """Format coverage report as human-readable string."""
        lines = []
        lines.append("=" * 80)
        lines.append("CODE COVERAGE REPORT")
        lines.append("=" * 80)
        lines.append(f"\nOverall Coverage: {report.total_coverage:.1f}%")
        lines.append(f"Line Coverage:    {report.line_coverage:.1f}%")
        lines.append(f"Branch Coverage:  {report.branch_coverage:.1f}%\n")

        if report.files:
            lines.append("FILE COVERAGE:")
            lines.append("-" * 80)
            lines.append(f"{'File':<50s} {'Coverage':>10s} {'Missing':>10s}")
            lines.append("-" * 80)

            for file_cov in sorted(report.files, key=lambda x: x.coverage_percent):
                lines.append(
                    f"{file_cov.file_path[:50]:<50s} "
                    f"{file_cov.coverage_percent:>9.1f}% "
                    f"{len(file_cov.missing_lines):>10d}"
                )

        if report.untested_functions:
            lines.append("\n⚠️  UNTESTED FUNCTIONS:")
            lines.append("-" * 80)
            for func in report.untested_functions[:10]:
                lines.append(f"  • {func.name} ({func.file_path}:{func.line_number})")

        if report.recommendations:
            lines.append("\n💡 RECOMMENDATIONS:")
            lines.append("-" * 80)
            for rec in report.recommendations:
                lines.append(f"  • {rec}")

        critical_gaps = self.identify_critical_gaps(report)
        if critical_gaps:
            lines.append("\n🚨 CRITICAL GAPS:")
            lines.append("-" * 80)
            for gap in critical_gaps:
                lines.append(f"  • {gap}")

        lines.append("\n" + "=" * 80)

        return "\n".join(lines)
