"""Core agent logic.

Restructured for clarity:
- agent.py - Main SharrowkinAgent with 5-phase cycle (LEGACY - use agent/core.py instead)
- types.py - Type definitions
- tools.py - Built-in tools
- llm/ - LLM integrations
- strategy/ - Connection strategies
- hooks/ - Hook system
- tool_system/ - Tool runner
"""

# Import from legacy location for backward compatibility
# TODO: Remove after migrating all imports to agent.core
try:
    from .agent import PHASES, SharrowkinAgent as LegacySharrowkinAgent
except ImportError:
    PHASES = ["Observe", "Recall", "Reason", "Stabilize", "Commit"]
    LegacySharrowkinAgent = None

from .llm import GeminiClient
from .strategy import SharrowkinAgentConfig, SharrowkinConnection
from .tools import (
    ProposedFileChange,
    apply_changes,
    fetch_url,
    git_diff,
    list_files,
    read_file,
    resolve_workspace,
    run_pytest,
    run_terminal_command,
    scan_workspace,
    search_web,
    summarize_workspace,
)
from .types import Step, StepStatus, StepType, ToolCall

__all__ = [
    "PHASES",
    "GeminiClient",
    "ProposedFileChange",
    "SharrowkinAgentConfig",
    "SharrowkinConnection",
    "Step",
    "StepStatus",
    "StepType",
    "ToolCall",
    "apply_changes",
    "fetch_url",
    "git_diff",
    "list_files",
    "read_file",
    "resolve_workspace",
    "run_pytest",
    "run_terminal_command",
    "scan_workspace",
    "search_web",
    "summarize_workspace",
]
