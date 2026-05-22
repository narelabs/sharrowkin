"""Debugger integration for automatic debugging.

Integrates with pdb/ipdb for:
- Automatic breakpoint placement
- Stack trace analysis
- Variable inspection
- Step-by-step execution
"""

import ast
import sys
import traceback
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class BreakpointStrategy(Enum):
    """Strategy for placing breakpoints."""
    ERROR_LINE = "error_line"  # At the line that raised exception
    FUNCTION_ENTRY = "function_entry"  # At function entry points
    BEFORE_CALL = "before_call"  # Before suspicious function calls
    VARIABLE_CHANGE = "variable_change"  # When variable changes


@dataclass
class BreakpointLocation:
    """Location for a breakpoint."""
    file_path: Path
    line_number: int
    function_name: Optional[str]
    reason: str
    strategy: BreakpointStrategy


@dataclass
class StackFrame:
    """Stack frame information."""
    file_path: Path
    line_number: int
    function_name: str
    code_context: List[str]
    local_vars: Dict[str, Any]


@dataclass
class DebugSession:
    """Debug session information."""
    exception_type: str
    exception_message: str
    stack_frames: List[StackFrame]
    breakpoints: List[BreakpointLocation]
    root_cause_analysis: str


class DebuggerIntegration:
    """Integrates with Python debuggers for automatic debugging."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.breakpoints: List[BreakpointLocation] = []

    def analyze_exception(self, exc_info: tuple) -> DebugSession:
        """Analyze exception and create debug session.
        
        Args:
            exc_info: Exception info from sys.exc_info()
            
        Returns:
            DebugSession with analysis and breakpoint suggestions
        """
        exc_type, exc_value, exc_tb = exc_info
        
        # Extract stack frames
        stack_frames = self._extract_stack_frames(exc_tb)
        
        # Suggest breakpoints
        breakpoints = self._suggest_breakpoints(stack_frames, exc_type, exc_value)
        
        # Analyze root cause
        root_cause = self._analyze_root_cause(stack_frames, exc_type, exc_value)
        
        return DebugSession(
            exception_type=exc_type.__name__,
            exception_message=str(exc_value),
            stack_frames=stack_frames,
            breakpoints=breakpoints,
            root_cause_analysis=root_cause,
        )

    def _extract_stack_frames(self, tb) -> List[StackFrame]:
        """Extract stack frames from traceback."""
        frames = []
        while tb is not None:
            frame = tb.tb_frame
            file_path = Path(frame.f_code.co_filename)
            
            # Only include frames from workspace
            if self._is_workspace_file(file_path):
                # Get code context
                try:
                    with open(file_path) as f:
                        lines = f.readlines()
                        line_num = tb.tb_lineno
                        start = max(0, line_num - 3)
                        end = min(len(lines), line_num + 2)
                        context = [lines[i].rstrip() for i in range(start, end)]
                except:
                    context = []
                
                frames.append(StackFrame(
                    file_path=file_path,
                    line_number=tb.tb_lineno,
                    function_name=frame.f_code.co_name,
                    code_context=context,
                    local_vars=dict(frame.f_locals),
                ))
            
            tb = tb.tb_next
        
        return frames

    def _suggest_breakpoints(self, frames: List[StackFrame], exc_type, exc_value) -> List[BreakpointLocation]:
        """Suggest breakpoint locations based on exception."""
        breakpoints = []
        
        if not frames:
            return breakpoints
        
        # Always add breakpoint at error line
        error_frame = frames[-1]
        breakpoints.append(BreakpointLocation(
            file_path=error_frame.file_path,
            line_number=error_frame.line_number,
            function_name=error_frame.function_name,
            reason=f"Exception raised: {exc_type.__name__}",
            strategy=BreakpointStrategy.ERROR_LINE,
        ))
        
        # Add breakpoint at function entry
        if len(frames) > 0:
            entry_frame = frames[0]
            breakpoints.append(BreakpointLocation(
                file_path=entry_frame.file_path,
                line_number=entry_frame.line_number,
                function_name=entry_frame.function_name,
                reason="Function entry point",
                strategy=BreakpointStrategy.FUNCTION_ENTRY,
            ))
        
        # Add breakpoints before suspicious calls
        for frame in frames[:-1]:
            if self._is_suspicious_call(frame, exc_type):
                breakpoints.append(BreakpointLocation(
                    file_path=frame.file_path,
                    line_number=frame.line_number,
                    function_name=frame.function_name,
                    reason="Suspicious call before error",
                    strategy=BreakpointStrategy.BEFORE_CALL,
                ))
        
        return breakpoints

    def _analyze_root_cause(self, frames: List[StackFrame], exc_type, exc_value) -> str:
        """Analyze root cause of exception."""
        if not frames:
            return "No stack frames available for analysis."
        
        error_frame = frames[-1]
        analysis = []
        
        # Exception type analysis
        if exc_type.__name__ == "AttributeError":
            analysis.append("AttributeError suggests accessing non-existent attribute or method.")
            analysis.append("Check if object is None or has expected attributes.")
        elif exc_type.__name__ == "KeyError":
            analysis.append("KeyError suggests accessing non-existent dictionary key.")
            analysis.append("Check if key exists before accessing or use .get() method.")
        elif exc_type.__name__ == "IndexError":
            analysis.append("IndexError suggests accessing out-of-bounds list/array index.")
            analysis.append("Check list length before accessing indices.")
        elif exc_type.__name__ == "TypeError":
            analysis.append("TypeError suggests incorrect type usage.")
            analysis.append("Check function arguments and return types.")
        elif exc_type.__name__ == "ValueError":
            analysis.append("ValueError suggests invalid value for operation.")
            analysis.append("Validate input values before processing.")
        
        # Variable analysis
        suspicious_vars = self._find_suspicious_variables(error_frame)
        if suspicious_vars:
            analysis.append(f"\nSuspicious variables: {', '.join(suspicious_vars)}")
        
        # Code context
        if error_frame.code_context:
            analysis.append(f"\nError occurred at: {error_frame.file_path}:{error_frame.line_number}")
            analysis.append(f"Function: {error_frame.function_name}")
        
        return "\n".join(analysis)

    def _is_workspace_file(self, file_path: Path) -> bool:
        """Check if file is in workspace."""
        try:
            file_path.relative_to(self.workspace_path)
            return True
        except ValueError:
            return False

    def _is_suspicious_call(self, frame: StackFrame, exc_type) -> bool:
        """Check if frame contains suspicious call."""
        # Simple heuristic: look for common error-prone patterns
        if not frame.code_context:
            return False
        
        code = " ".join(frame.code_context).lower()
        
        # Check for common patterns
        if exc_type.__name__ == "AttributeError" and "." in code:
            return True
        if exc_type.__name__ == "KeyError" and "[" in code:
            return True
        if exc_type.__name__ == "IndexError" and "[" in code:
            return True
        
        return False

    def _find_suspicious_variables(self, frame: StackFrame) -> List[str]:
        """Find variables that might be causing issues."""
        suspicious = []
        
        for var_name, var_value in frame.local_vars.items():
            # Skip internal variables
            if var_name.startswith("_"):
                continue
            
            # Check for None
            if var_value is None:
                suspicious.append(f"{var_name}=None")
            # Check for empty collections
            elif isinstance(var_value, (list, dict, set)) and len(var_value) == 0:
                suspicious.append(f"{var_name}=empty")
        
        return suspicious

    def generate_debug_script(self, session: DebugSession, output_path: Path) -> None:
        """Generate pdb debug script.
        
        Args:
            session: Debug session with breakpoints
            output_path: Path to save debug script
        """
        script_lines = [
            "# Auto-generated debug script",
            "import pdb",
            "import sys",
            "",
            "# Set breakpoints",
        ]
        
        for bp in session.breakpoints:
            script_lines.append(
                f"pdb.set_trace()  # {bp.reason} at {bp.file_path}:{bp.line_number}"
            )
        
        script_lines.extend([
            "",
            "# Root cause analysis:",
            f"# {session.root_cause_analysis.replace(chr(10), chr(10) + '# ')}",
        ])
        
        output_path.write_text("\n".join(script_lines))
