"""Local workspace tools for Sharrowkin."""

from __future__ import annotations

import ast
import difflib
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
for relative in ("integrations/semanticgit/src",):
    candidate = BACKEND_DIR / relative
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from sgit.parsers.ast_parser import parse_file as parse_semantic_file
except Exception:
    parse_semantic_file = None

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".sharrowkin",
    "__pycache__",
    "dist",
    "node_modules",
    "venv",
    ".venv",
    "blocksuite",
    "benchmarks",
    "devin_transfer",
    "shrrowkincleanui",
    "build",
    "public",
}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".toml", ".yml", ".yaml", ".css"}
BLOCKED_COMMAND_TOKENS = {
    "curl",
    "wget",
    "nc",
    "netcat",
    "ssh",
    "scp",
    "rsync",
    "sudo",
    "su",
    "chmod",
    "chown",
    "rm",
    "mkfs",
    "dd",
    "git",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
}
SHELL_CONTROL_TOKENS = {"&&", "||", ";", "|", "`", "$("}


@dataclass(slots=True)
class SymbolSummary:
    kind: str
    name: str
    signature: str
    line: int


@dataclass(slots=True)
class FileSummary:
    path: str
    language: str
    line_count: int = 0
    imports: list[str] = field(default_factory=list)
    symbols: list[SymbolSummary] = field(default_factory=list)
    error: str = ""


@dataclass(slots=True)
class ProposedFileChange:
    path: str
    content: str


@dataclass(slots=True)
class PatchResult:
    diff: str
    changed_files: list[str]


@dataclass(slots=True)
class TestResult:
    success: bool
    exit_code: int
    output: str


def resolve_workspace(workspace_path: str) -> Path:
    workspace = Path(workspace_path).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise FileNotFoundError(f"Workspace does not exist or is not a directory: {workspace}")
    return workspace


def safe_relative_path(workspace: Path, candidate: str) -> Path:
    rel = Path(candidate)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe patch path: {candidate}")
    target = (workspace / rel).resolve()
    if workspace not in target.parents and target != workspace:
        raise ValueError(f"Patch path escapes workspace: {candidate}")
    return target


def split_safe_command(command: str) -> list[str]:
    if any(token in command for token in SHELL_CONTROL_TOKENS):
        raise ValueError("Shell control operators are blocked")
    parts = shlex.split(command)
    if not parts:
        raise ValueError("Empty command")
    blocked = BLOCKED_COMMAND_TOKENS & {Path(part).name.lower() for part in parts}
    if blocked:
        raise ValueError(f"Command token blocked: {', '.join(sorted(blocked))}")
    return parts


def iter_source_files(workspace: Path, max_files: int = 160) -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(workspace):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        root_path = Path(root)
        for name in sorted(names):
            path = root_path / name
            if path.suffix not in TEXT_SUFFIXES or path.stat().st_size > 200_000:
                continue
            files.append(path)
            if len(files) >= max_files:
                return files
    return files


def read_file(workspace: Path, relative_path: str, max_lines: int = 500) -> str:
    """Read a file from the workspace and return its content."""
    target = safe_relative_path(workspace, relative_path)
    if not target.exists():
        return f"ERROR: File not found: {relative_path}"
    if target.stat().st_size > 300_000:
        return f"ERROR: File too large: {relative_path} ({target.stat().st_size} bytes)"
    content = target.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n... [{len(lines) - max_lines} more lines truncated]"
    return content


def list_files(workspace: Path, subdir: str = "") -> str:
    """List files in a workspace subdirectory."""
    target = workspace / subdir if subdir else workspace
    if not target.exists():
        return f"ERROR: Directory not found: {subdir}"
    entries = []
    for item in sorted(target.iterdir()):
        if item.name in IGNORED_DIRS or item.name.startswith("."):
            continue
        prefix = "📁" if item.is_dir() else "📄"
        size = ""
        if item.is_file():
            size = f" ({item.stat().st_size:,} bytes)"
        entries.append(f"{prefix} {item.name}{size}")
    return "\n".join(entries) if entries else "(empty directory)"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _annotation_text(annotation: ast.expr | None) -> str:
    if annotation is None:
        return ""
    return ast.unparse(annotation)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    parts: list[str] = []
    for arg in node.args.posonlyargs:
        parts.append(arg.arg)
    if node.args.posonlyargs:
        parts.append("/")
    for arg in node.args.args:
        annotation = _annotation_text(arg.annotation)
        parts.append(f"{arg.arg}: {annotation}" if annotation else arg.arg)
    if node.args.vararg:
        parts.append(f"*{node.args.vararg.arg}")
    elif node.args.kwonlyargs:
        parts.append("*")
    for arg in node.args.kwonlyargs:
        annotation = _annotation_text(arg.annotation)
        parts.append(f"{arg.arg}: {annotation}" if annotation else arg.arg)
    if node.args.kwarg:
        parts.append(f"**{node.args.kwarg.arg}")
    returns = _annotation_text(node.returns)
    suffix = f" -> {returns}" if returns else ""
    return f"({', '.join(parts)}){suffix}"


def _append_semantic_node(summary: FileSummary, node) -> None:
    if node.kind == "import":
        summary.imports.append(node.name)
        return
    summary.symbols.append(
        SymbolSummary(node.kind, node.qualified_name, node.signature, node.line_start)
    )
    for child in node.children:
        _append_semantic_node(summary, child)


def parse_python_summary(relative_path: str, source: str) -> FileSummary:
    summary = FileSummary(path=relative_path, language="python", line_count=len(source.splitlines()))
    if parse_semantic_file is not None:
        snapshot = parse_semantic_file(relative_path, source)
        for node in snapshot.nodes:
            _append_semantic_node(summary, node)
        return summary

    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError as exc:
        summary.error = f"SyntaxError: {exc}"
        return summary

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                summary.imports.extend(alias.name for alias in node.names)
            else:
                module = node.module or ""
                summary.imports.append(module)
        elif isinstance(node, ast.ClassDef):
            summary.symbols.append(SymbolSummary("class", node.name, "", node.lineno))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "async_method" if isinstance(child, ast.AsyncFunctionDef) else "method"
                    summary.symbols.append(
                        SymbolSummary(kind, f"{node.name}.{child.name}", _function_signature(child), child.lineno)
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            summary.symbols.append(SymbolSummary(kind, node.name, _function_signature(node), node.lineno))
    return summary


def scan_workspace(workspace: Path) -> list[FileSummary]:
    """
    Scan workspace and extract structure from all source files.

    This tool performs AST-level analysis of the codebase to understand its structure.
    Use it at the beginning of a task to understand what code exists.

    Args:
        workspace: Absolute path to the project root directory

    Returns:
        List of FileSummary objects, each containing:
        - path: Relative file path (e.g., "src/main.py")
        - language: File extension (e.g., "py", "ts", "js")
        - line_count: Number of lines in the file
        - imports: List of imported modules (Python only)
        - symbols: List of top-level symbols (classes, functions, etc.)
        - error: Parse error message if file couldn't be analyzed

    What gets scanned:
        - Python files (.py): Full AST analysis with imports, classes, functions
        - TypeScript/JavaScript (.ts, .tsx, .js, .jsx): Basic structure
        - Config files (.json, .yaml, .toml, .md): Line counts only
        - Ignores: node_modules, venv, __pycache__, .git, dist, build

    Example usage:
        summaries = scan_workspace(Path("/project"))
        for summary in summaries:
            print(f"{summary.path}: {len(summary.symbols)} symbols")

    Best practices:
        - Run this ONCE at the start of a task to understand the codebase
        - Don't run repeatedly - it's expensive (scans all files)
        - Use the results to understand project structure before making changes
        - Check summary.imports to understand dependencies
        - Check summary.symbols to find classes and functions

    Performance note:
        - Scans all source files (can be 100+ files)
        - Takes 1-3 seconds on typical projects
        - Results are cached by the agent system
    """
    summaries: list[FileSummary] = []
    for path in iter_source_files(workspace):
        relative_path = path.relative_to(workspace).as_posix()
        source = read_text(path)
        if path.suffix == ".py":
            summaries.append(parse_python_summary(relative_path, source))
        else:
            summaries.append(FileSummary(path=relative_path, language=path.suffix.lstrip("."), line_count=len(source.splitlines())))
    return summaries


def summarize_workspace(summaries: list[FileSummary], max_files: int = 60) -> str:
    lines: list[str] = []
    for summary in summaries[:max_files]:
        lines.append(f"FILE {summary.path} [{summary.language}]")
        if summary.error:
            lines.append(f"  error: {summary.error}")
        if summary.imports:
            imports = ", ".join(sorted(set(summary.imports))[:5])
            lines.append(f"  imports: {imports}")
        # Only list top-level or important symbols, max 8 per file, without full signatures to save tokens
        for symbol in summary.symbols[:8]:
            # Keep it simple: "class MyClass" or "function my_func"
            name_only = symbol.name.split('(')[0]
            lines.append(f"  {symbol.kind} {name_only}")
    if len(summaries) > max_files:
        lines.append(f"... {len(summaries) - max_files} more files omitted")
    return "\n".join(lines)


def apply_changes(workspace: Path, changes: list[ProposedFileChange]) -> PatchResult:
    """
    Apply file changes to the workspace (create, modify, or overwrite files).

    This is the PRIMARY tool for making code changes. Use it to create new files,
    modify existing files, or update multiple files at once.

    Args:
        workspace: Absolute path to the project root directory
        changes: List of ProposedFileChange objects, each containing:
            - path: Relative path from workspace (e.g., "src/main.py", "README.md")
            - content: Complete new file content (NOT a diff - full file text)

    Returns:
        PatchResult with:
        - diff: Unified diff showing what changed (git diff format)
        - changed_files: List of file paths that were actually modified

    CRITICAL RULES:
        1. ALWAYS provide COMPLETE file content, not partial changes
        2. Use RELATIVE paths from workspace root (e.g., "src/app.py", NOT "/home/user/project/src/app.py")
        3. If file doesn't exist, it will be created
        4. If file exists, it will be COMPLETELY REPLACED with new content
        5. Preserve existing code you don't want to change - include it in content

    Example usage:
        # Create a new file
        changes = [
            ProposedFileChange(
                path="src/hello.py",
                content="def hello():\n    print('Hello, world!')\n"
            )
        ]
        result = apply_changes(Path("/project"), changes)

        # Modify existing file (provide FULL content)
        changes = [
            ProposedFileChange(
                path="README.md",
                content="# My Project\n\nThis is the updated README.\n"
            )
        ]
        result = apply_changes(Path("/project"), changes)

        # Update multiple files at once
        changes = [
            ProposedFileChange(path="src/main.py", content="...full content..."),
            ProposedFileChange(path="src/utils.py", content="...full content..."),
        ]
        result = apply_changes(Path("/project"), changes)

    Best practices:
        - Read the file first if you need to preserve existing code
        - Provide complete file content, not just the changed lines
        - Use relative paths (src/file.py) not absolute (/home/user/project/src/file.py)
        - Check result.diff to see what actually changed
        - Run tests after applying changes to verify nothing broke

    Common mistakes to AVOID:
        ❌ Providing only changed lines (must provide FULL file)
        ❌ Using absolute paths (use relative from workspace)
        ❌ Forgetting to include unchanged code (file will be truncated)
        ❌ Not reading existing file before modifying it
    """
    originals: dict[str, str] = {}
    next_contents: dict[str, str] = {}
    changed_files: list[str] = []
    for change in changes:
        target = safe_relative_path(workspace, change.path)
        original = read_text(target) if target.exists() else ""
        originals[change.path] = original
        next_contents[change.path] = change.content
        if original != change.content:
            changed_files.append(change.path)

    diff = unified_diff(originals, next_contents)
    for change in changes:
        if change.path in changed_files:
            write_text(safe_relative_path(workspace, change.path), change.content)
    return PatchResult(diff=diff, changed_files=changed_files)


def unified_diff(originals: dict[str, str], next_contents: dict[str, str]) -> str:
    chunks: list[str] = []
    for path in sorted(next_contents):
        before = originals.get(path, "").splitlines(keepends=True)
        after = next_contents[path].splitlines(keepends=True)
        chunks.extend(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
    return "\n".join(chunks)


def git_diff(workspace: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--"],
        cwd=workspace,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    return result.stdout


def run_pytest(workspace: Path, timeout_seconds: int = 300) -> TestResult:
    """
    Run pytest test suite in the workspace directory.

    This tool executes all tests found by pytest in the workspace. Use this to validate
    that your code changes don't break existing functionality.

    Args:
        workspace: Absolute path to the project root directory
        timeout_seconds: Maximum time to wait for tests (default: 300s / 5 minutes)

    Returns:
        TestResult with:
        - success: True if all tests passed (exit code 0) or no tests found (exit code 5)
        - exit_code: pytest exit code (0=passed, 1=failed, 5=no tests)
        - output: Last 12,000 chars of test output (stdout + stderr combined)

    Common exit codes:
        0 - All tests passed
        1 - Tests failed
        2 - Test execution interrupted
        3 - Internal error
        4 - pytest command line usage error
        5 - No tests collected (treated as success)

    Example usage:
        result = run_pytest(Path("/home/user/project"))
        if result.success:
            print("All tests passed!")
        else:
            print(f"Tests failed with exit code {result.exit_code}")
            print(result.output)

    Best practices:
        - Always run tests after making code changes
        - Check result.success before proceeding
        - If tests fail, read result.output to understand what broke
        - Fix failing tests before moving to next task
    """
    result = subprocess.run(
        ["python", "-m", "pytest"],
        cwd=workspace,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_seconds,
        check=False,
    )
    output = result.stdout[-12_000:]
    no_tests_collected = result.returncode == 5 and "no tests" in output.lower()
    return TestResult(success=result.returncode == 0 or no_tests_collected, exit_code=result.returncode, output=output)


import urllib.request
import urllib.parse
import re

def search_web(query: str, limit: int = 5) -> str:
    """Search the web for documentation or answers using DuckDuckGo."""
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        req = urllib.request.Request(
            url, 
            data=None, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        results = []
        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        urls = re.findall(r'<a class="result__url" href="([^"]+)">', html, re.IGNORECASE)
        
        for i in range(min(limit, len(snippets), len(urls))):
            text = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            results.append(f"{i+1}. {urls[i]}\n   {text}")
            
        if not results:
            return "No web results found."
        return "\n\n".join(results)
    except Exception as e:
        return f"Web search failed: {str(e)}"

def fetch_url(url: str) -> str:
    """Fetch and extract text content from a URL."""
    try:
        req = urllib.request.Request(
            url, 
            data=None, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text[:10000]
    except Exception as e:
        return f"Failed to fetch URL: {str(e)}"


def run_terminal_command(workspace: Path, command: str, timeout_seconds: int = 120) -> TestResult:
    """
    Execute a shell command in the workspace directory with safety filtering.

    This tool runs terminal commands like npm install, git status, or custom scripts.
    Commands are filtered for security - network tools (curl, wget, nc) are blocked.

    Args:
        workspace: Absolute path to the project root (command runs in this directory)
        command: Shell command to execute (e.g., "npm install", "git status")
        timeout_seconds: Maximum execution time (default: 120s / 2 minutes)

    Returns:
        TestResult with:
        - success: True if exit code is 0
        - exit_code: Command exit code (0=success, non-zero=error, -1=timeout, -2=execution failed)
        - output: Combined stdout and stderr

    Security restrictions:
        - Blocked commands: curl, wget, nc, netcat (network tools)
        - No shell injection - commands are parsed safely
        - Runs in workspace directory only

    Example usage:
        # Install dependencies
        result = run_terminal_command(Path("/project"), "npm install")

        # Check git status
        result = run_terminal_command(Path("/project"), "git status")

        # Run build script
        result = run_terminal_command(Path("/project"), "npm run build")

    Best practices:
        - Use absolute paths in workspace parameter (not relative)
        - Check result.success before assuming command worked
        - Read result.output to understand errors
        - Avoid chaining commands with && - run separately for better error handling
        - Don't use network commands (curl, wget) - they're blocked for security

    Common errors:
        - Exit code -1: Command timed out (increase timeout_seconds)
        - Exit code -2: Command execution failed (check command syntax)
        - Exit code 127: Command not found (check if tool is installed)
    """
    try:
        argv = split_safe_command(command)
        result = subprocess.run(
            argv,
            cwd=workspace,
            shell=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
        return TestResult(
            success=result.returncode == 0,
            exit_code=result.returncode,
            output=result.stdout or "Command completed with no output."
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            success=False,
            exit_code=-1,
            output=f"Command timed out after {timeout_seconds} seconds."
        )
    except Exception as e:
        return TestResult(
            success=False,
            exit_code=-2,
            output=f"Failed to execute command: {str(e)}"
        )


# GitHub API Tools
async def github_list_repos(token: str) -> str:
    """List GitHub repositories for authenticated user.

    Args:
        token: GitHub access token from localStorage

    Returns:
        JSON string with list of repositories
    """
    try:
        from integrations.github import GitHubAPI

        api = GitHubAPI(token)
        repos = await api.list_repos()

        # Format for display
        result = []
        for repo in repos:
            result.append({
                "name": repo["name"],
                "full_name": repo["full_name"],
                "private": repo["private"],
                "description": repo.get("description", ""),
                "url": repo["html_url"],
                "default_branch": repo.get("default_branch", "main"),
                "language": repo.get("language", ""),
                "stars": repo.get("stargazers_count", 0),
                "updated_at": repo.get("updated_at", "")
            })

        import json
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing repositories: {str(e)}"


async def github_get_repo_info(token: str, owner: str, repo: str) -> str:
    """Get detailed information about a GitHub repository.

    Args:
        token: GitHub access token
        owner: Repository owner
        repo: Repository name

    Returns:
        JSON string with repository details
    """
    try:
        from integrations.github import GitHubAPI

        api = GitHubAPI(token)
        repo_data = await api.get_repo(owner, repo)

        import json
        return json.dumps(repo_data, indent=2)
    except Exception as e:
        return f"Error getting repository info: {str(e)}"


async def github_list_branches(token: str, owner: str, repo: str) -> str:
    """List branches in a GitHub repository.

    Args:
        token: GitHub access token
        owner: Repository owner
        repo: Repository name

    Returns:
        JSON string with list of branches
    """
    try:
        from integrations.github import GitHubAPI

        api = GitHubAPI(token)
        branches = await api.list_branches(owner, repo)

        import json
        return json.dumps(branches, indent=2)
    except Exception as e:
        return f"Error listing branches: {str(e)}"


async def github_create_pr(
    token: str,
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main"
) -> str:
    """Create a pull request on GitHub.

    Args:
        token: GitHub access token
        owner: Repository owner
        repo: Repository name
        title: PR title
        body: PR description
        head: Branch with changes
        base: Target branch (default: main)

    Returns:
        JSON string with PR details
    """
    try:
        from integrations.github import GitHubAPI

        api = GitHubAPI(token)
        pr = await api.create_pr(owner, repo, title, body, head, base)

        import json
        return json.dumps(pr, indent=2)
    except Exception as e:
        return f"Error creating PR: {str(e)}"


async def github_clone_repo(
    token: str,
    owner: str,
    repo: str,
    workspace: str = "/tmp/sharrowkin-workspace"
) -> str:
    """Clone a GitHub repository to server workspace.

    Args:
        token: GitHub access token
        owner: Repository owner
        repo: Repository name
        workspace: Server workspace path

    Returns:
        Success message with cloned path
    """
    try:
        import subprocess
        from pathlib import Path

        # Create repos directory if it doesn't exist
        repos_dir = Path(workspace) / "repos"
        repos_dir.mkdir(parents=True, exist_ok=True)

        # Target path for cloned repo
        repo_path = repos_dir / repo

        # Check if already cloned
        if repo_path.exists():
            # Pull latest changes
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return f"Repository already cloned at {repo_path}. Pulled latest changes."
            else:
                return f"Repository exists at {repo_path} but failed to pull: {result.stderr}"

        # Clone repository with token authentication
        clone_url = f"https://{token}@github.com/{owner}/{repo}.git"
        result = subprocess.run(
            ["git", "clone", clone_url, str(repo_path)],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            # Count files
            file_count = sum(1 for _ in repo_path.rglob("*") if _.is_file())
            return f"✅ Successfully cloned {owner}/{repo} to {repo_path}\n📁 {file_count} files"
        else:
            return f"❌ Failed to clone repository: {result.stderr}"

    except subprocess.TimeoutExpired:
        return "❌ Clone operation timed out (>2 minutes)"
    except Exception as e:
        return f"❌ Error cloning repository: {str(e)}"

