"""Tools module - Agent tools organized by category."""

# Re-export from core/tools.py for backward compatibility
from backend.core.tools import (
    # Classes
    SymbolSummary,
    FileSummary,
    ProposedFileChange,
    PatchResult,
    TestResult,

    # Workspace
    resolve_workspace,
    safe_relative_path,
    iter_source_files,
    scan_workspace,
    summarize_workspace,

    # Files
    read_file,
    list_files,
    read_text,
    write_text,

    # Git
    git_diff,
    apply_changes,
    unified_diff,

    # Testing
    run_pytest,

    # Web
    search_web,
    fetch_url,

    # Terminal
    run_terminal_command,
    split_safe_command,

    # GitHub (imported from integrations)
    github_list_repos,
    github_get_repo_info,
    github_list_branches,
    github_create_pr,
    github_clone_repo,
)

__all__ = [
    # Classes
    "SymbolSummary",
    "FileSummary",
    "ProposedFileChange",
    "PatchResult",
    "TestResult",

    # Workspace
    "resolve_workspace",
    "safe_relative_path",
    "iter_source_files",
    "scan_workspace",
    "summarize_workspace",

    # Files
    "read_file",
    "list_files",
    "read_text",
    "write_text",

    # Git
    "git_diff",
    "apply_changes",
    "unified_diff",

    # Testing
    "run_pytest",

    # Web
    "search_web",
    "fetch_url",

    # Terminal
    "run_terminal_command",
    "split_safe_command",

    # GitHub
    "github_list_repos",
    "github_get_repo_info",
    "github_list_branches",
    "github_create_pr",
    "github_clone_repo",
]
