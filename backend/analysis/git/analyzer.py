import subprocess
from pathlib import Path
from typing import Any


class GitAnalyzer:
    """Retrieves Git history metadata, modified count, and hotspots."""

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path = workspace_path
        self.is_git = self._check_git_repo()

    def _check_git_repo(self) -> bool:
        """Verify if the workspace is a Git repository."""
        git_dir = self.workspace_path / ".git"
        if not git_dir.exists():
            return False
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.workspace_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            return res.returncode == 0
        except Exception:
            return False

    def get_recent_commits(self, limit: int = 10) -> list[dict[str, str]]:
        """Get list of recent commits."""
        if not self.is_git:
            return []

        try:
            # Format: hash | author | relative_date | subject
            res = subprocess.run(
                ["git", "log", f"-n", str(limit), "--pretty=format:%h|%an|%ar|%s"],
                cwd=str(self.workspace_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False
            )
            if res.returncode != 0 or not res.stdout:
                return []

            commits = []
            for line in res.stdout.strip().split("\n"):
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3]
                    })
            return commits
        except Exception:
            return []

    def get_hotspots(self, limit: int = 5) -> list[tuple[str, int]]:
        """Identify top modified files (hotspots) in history."""
        if not self.is_git:
            return []

        try:
            # Get list of all modified files from git log
            res = subprocess.run(
                ["git", "log", "--name-only", "--pretty=format:"],
                cwd=str(self.workspace_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False
            )
            if res.returncode != 0 or not res.stdout:
                return []

            file_counts = {}
            for line in res.stdout.strip().split("\n"):
                line = line.strip()
                # Filter empty lines, git configs, or tests if we only want code, but let's count all files
                if line and Path(self.workspace_path / line).exists():
                    file_counts[line] = file_counts.get(line, 0) + 1

            sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
            return sorted_files[:limit]
        except Exception:
            return []

    def get_file_metadata(self, file_path: str) -> dict[str, Any]:
        """Get git metadata for a specific file."""
        if not self.is_git:
            return {}

        try:
            # Get last author and commit date for file
            res = subprocess.run(
                ["git", "log", "-n", "1", "--pretty=format:%an|%ar|%s", "--", file_path],
                cwd=str(self.workspace_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False
            )
            
            # Get total change count for file
            count_res = subprocess.run(
                ["git", "rev-list", "--count", "HEAD", "--", file_path],
                cwd=str(self.workspace_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )

            metadata = {}
            if res.returncode == 0 and res.stdout:
                parts = res.stdout.strip().split("|")
                if len(parts) == 3:
                    metadata["last_author"] = parts[0]
                    metadata["last_change"] = parts[1]
                    metadata["last_commit_msg"] = parts[2]
            
            if count_res.returncode == 0 and count_res.stdout:
                try:
                    metadata["change_count"] = int(count_res.stdout.strip())
                except ValueError:
                    metadata["change_count"] = 0
            
            return metadata
        except Exception:
            return {}
