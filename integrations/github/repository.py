"""GitHub repository management with local git operations.

Handles cloning, pulling, pushing, and branch management.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class GitHubRepository:
    """Local git repository manager for GitHub repos."""

    def __init__(self, repo_path: Path | str):
        """Initialize repository manager.

        Args:
            repo_path: Path to local repository
        """
        self.repo_path = Path(repo_path)

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run git command in repository.

        Args:
            *args: Git command arguments
            check: Raise exception on non-zero exit code

        Returns:
            CompletedProcess result
        """
        return subprocess.run(
            ["git", "-C", str(self.repo_path), *args],
            capture_output=True,
            text=True,
            check=check,
        )

    @classmethod
    def clone(
        cls,
        repo_url: str,
        dest_path: Path | str,
        branch: str | None = None,
        depth: int | None = None,
    ) -> GitHubRepository:
        """Clone a GitHub repository.

        Args:
            repo_url: GitHub repository URL (https or ssh)
            dest_path: Destination directory
            branch: Specific branch to clone
            depth: Shallow clone depth (None for full history)

        Returns:
            GitHubRepository instance for cloned repo

        Raises:
            subprocess.CalledProcessError: If clone fails
        """
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "clone"]
        if branch:
            cmd.extend(["--branch", branch])
        if depth:
            cmd.extend(["--depth", str(depth)])
        cmd.extend([repo_url, str(dest_path)])

        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return cls(dest_path)

    def get_current_branch(self) -> str:
        """Get current branch name."""
        result = self._run_git("branch", "--show-current")
        return result.stdout.strip()

    def list_branches(self, remote: bool = False) -> list[str]:
        """List branches.

        Args:
            remote: List remote branches instead of local

        Returns:
            List of branch names
        """
        args = ["branch", "-r"] if remote else ["branch"]
        result = self._run_git(*args)
        branches = []
        for line in result.stdout.splitlines():
            branch = line.strip().lstrip("* ").strip()
            if remote:
                # Remove "origin/" prefix
                branch = branch.split("/", 1)[-1] if "/" in branch else branch
            if branch and branch != "HEAD":
                branches.append(branch)
        return branches

    def create_branch(self, branch_name: str, from_branch: str | None = None) -> None:
        """Create a new branch.

        Args:
            branch_name: Name for new branch
            from_branch: Source branch (current branch if None)
        """
        if from_branch:
            self._run_git("checkout", from_branch)
        self._run_git("checkout", "-b", branch_name)

    def switch_branch(self, branch_name: str) -> None:
        """Switch to a different branch.

        Args:
            branch_name: Branch to switch to
        """
        self._run_git("checkout", branch_name)

    def delete_branch(self, branch_name: str, force: bool = False) -> None:
        """Delete a branch.

        Args:
            branch_name: Branch to delete
            force: Force delete even if not merged
        """
        flag = "-D" if force else "-d"
        self._run_git("branch", flag, branch_name)

    def pull(self, remote: str = "origin", branch: str | None = None) -> str:
        """Pull changes from remote.

        Args:
            remote: Remote name
            branch: Branch to pull (current branch if None)

        Returns:
            Git pull output
        """
        args = ["pull", remote]
        if branch:
            args.append(branch)
        result = self._run_git(*args)
        return result.stdout

    def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        set_upstream: bool = False,
        force: bool = False,
    ) -> str:
        """Push changes to remote.

        Args:
            remote: Remote name
            branch: Branch to push (current branch if None)
            set_upstream: Set upstream tracking
            force: Force push

        Returns:
            Git push output
        """
        args = ["push"]
        if set_upstream:
            args.append("--set-upstream")
        if force:
            args.append("--force")
        args.append(remote)
        if branch:
            args.append(branch)
        result = self._run_git(*args)
        return result.stdout

    def commit(self, message: str, files: list[str] | None = None) -> str:
        """Create a commit.

        Args:
            message: Commit message
            files: Specific files to commit (all staged if None)

        Returns:
            Commit SHA
        """
        if files:
            self._run_git("add", *files)
        else:
            self._run_git("add", "-A")

        self._run_git("commit", "-m", message)
        result = self._run_git("rev-parse", "HEAD")
        return result.stdout.strip()

    def get_status(self) -> dict[str, Any]:
        """Get repository status.

        Returns:
            Dict with status information
        """
        result = self._run_git("status", "--porcelain")
        lines = result.stdout.splitlines()

        status = {
            "modified": [],
            "added": [],
            "deleted": [],
            "untracked": [],
            "renamed": [],
        }

        for line in lines:
            if not line:
                continue
            code = line[:2]
            filepath = line[3:]

            if code == "??":
                status["untracked"].append(filepath)
            elif "M" in code:
                status["modified"].append(filepath)
            elif "A" in code:
                status["added"].append(filepath)
            elif "D" in code:
                status["deleted"].append(filepath)
            elif "R" in code:
                status["renamed"].append(filepath)

        return status

    def get_diff(self, staged: bool = False) -> str:
        """Get diff of changes.

        Args:
            staged: Show staged changes instead of unstaged

        Returns:
            Diff output
        """
        args = ["diff"]
        if staged:
            args.append("--staged")
        result = self._run_git(*args)
        return result.stdout

    def get_log(self, max_count: int = 10, format: str = "oneline") -> list[str]:
        """Get commit log.

        Args:
            max_count: Maximum number of commits
            format: Log format (oneline, short, medium, full)

        Returns:
            List of commit log entries
        """
        result = self._run_git(
            "log",
            f"--max-count={max_count}",
            f"--format={format}",
        )
        return result.stdout.splitlines()

    def get_remote_url(self, remote: str = "origin") -> str:
        """Get remote URL.

        Args:
            remote: Remote name

        Returns:
            Remote URL
        """
        result = self._run_git("remote", "get-url", remote)
        return result.stdout.strip()

    def set_remote_url(self, url: str, remote: str = "origin") -> None:
        """Set remote URL.

        Args:
            url: New remote URL
            remote: Remote name
        """
        self._run_git("remote", "set-url", remote, url)

    def fetch(self, remote: str = "origin", prune: bool = True) -> str:
        """Fetch from remote.

        Args:
            remote: Remote name
            prune: Remove deleted remote branches

        Returns:
            Fetch output
        """
        args = ["fetch", remote]
        if prune:
            args.append("--prune")
        result = self._run_git(*args)
        return result.stdout

    def is_clean(self) -> bool:
        """Check if working directory is clean (no uncommitted changes)."""
        result = self._run_git("status", "--porcelain")
        return not result.stdout.strip()

    def get_config(self, key: str) -> str | None:
        """Get git config value.

        Args:
            key: Config key (e.g., user.name)

        Returns:
            Config value or None if not set
        """
        result = self._run_git("config", "--get", key, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def set_config(self, key: str, value: str, global_: bool = False) -> None:
        """Set git config value.

        Args:
            key: Config key
            value: Config value
            global_: Set globally instead of repo-local
        """
        args = ["config"]
        if global_:
            args.append("--global")
        args.extend([key, value])
        self._run_git(*args)
