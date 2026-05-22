"""GitHub API wrapper for repository operations.

Provides high-level interface for GitHub REST API v3.
"""

from __future__ import annotations

from typing import Any

import httpx


class GitHubAPI:
    """GitHub REST API client."""

    def __init__(self, access_token: str):
        """Initialize GitHub API client.

        Args:
            access_token: GitHub personal access token or OAuth token
        """
        self.access_token = access_token
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_user(self) -> dict[str, Any]:
        """Get authenticated user information."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.api_base}/user", headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def list_repos(
        self,
        visibility: str = "all",
        sort: str = "updated",
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """List repositories for authenticated user.

        Args:
            visibility: all, public, or private
            sort: created, updated, pushed, full_name
            per_page: Results per page (max 100)

        Returns:
            List of repository objects
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/user/repos",
                headers=self.headers,
                params={"visibility": visibility, "sort": sort, "per_page": per_page},
            )
            response.raise_for_status()
            return response.json()

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Get repository information.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository object
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_contents(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: str = "main",
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Get contents of a file or directory.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to file or directory (empty for root)
            ref: Branch, tag, or commit SHA

        Returns:
            File object or list of directory contents
        """
        async with httpx.AsyncClient() as client:
            url = f"{self.api_base}/repos/{owner}/{repo}/contents/{path}"
            params = {"ref": ref} if ref else {}
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = "main",
    ) -> str:
        """Get decoded content of a file.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to file
            ref: Branch, tag, or commit SHA

        Returns:
            Decoded file content as string
        """
        import base64

        contents = await self.get_contents(owner, repo, path, ref)
        if isinstance(contents, list):
            raise ValueError(f"Path {path} is a directory, not a file")

        if contents.get("encoding") == "base64":
            content = base64.b64decode(contents["content"]).decode("utf-8")
            return content
        else:
            return contents.get("content", "")

    async def get_tree(
        self,
        owner: str,
        repo: str,
        sha: str = "main",
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Get repository tree (file structure).

        Args:
            owner: Repository owner
            repo: Repository name
            sha: Branch, tag, or commit SHA
            recursive: Fetch tree recursively

        Returns:
            Tree object with file structure
        """
        async with httpx.AsyncClient() as client:
            # First get the commit to get tree SHA
            commit_response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}/commits/{sha}",
                headers=self.headers,
            )
            commit_response.raise_for_status()
            tree_sha = commit_response.json()["commit"]["tree"]["sha"]

            # Then get the tree
            params = {"recursive": "1"} if recursive else {}
            response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}/git/trees/{tree_sha}",
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a file in repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to file
            content: File content (will be base64 encoded)
            message: Commit message
            branch: Branch to commit to
            sha: SHA of file being replaced (required for updates)

        Returns:
            Commit object
        """
        import base64

        async with httpx.AsyncClient() as client:
            encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            data = {
                "message": message,
                "content": encoded_content,
                "branch": branch,
            }
            if sha:
                data["sha"] = sha

            response = await client.put(
                f"{self.api_base}/repos/{owner}/{repo}/contents/{path}",
                headers=self.headers,
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def list_branches(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """List branches in repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            List of branch objects
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}/branches",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def create_branch(
        self,
        owner: str,
        repo: str,
        branch: str,
        from_branch: str = "main",
    ) -> dict[str, Any]:
        """Create a new branch.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: New branch name
            from_branch: Source branch to branch from

        Returns:
            Reference object
        """
        # Get SHA of source branch
        async with httpx.AsyncClient() as client:
            ref_response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}/git/ref/heads/{from_branch}",
                headers=self.headers,
            )
            ref_response.raise_for_status()
            sha = ref_response.json()["object"]["sha"]

            # Create new branch
            response = await client.post(
                f"{self.api_base}/repos/{owner}/{repo}/git/refs",
                headers=self.headers,
                json={"ref": f"refs/heads/{branch}", "sha": sha},
            )
            response.raise_for_status()
            return response.json()

    async def create_pr(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            title: PR title
            head: Branch containing changes
            base: Branch to merge into
            body: PR description
            draft: Create as draft PR

        Returns:
            Pull request object
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/repos/{owner}/{repo}/pulls",
                headers=self.headers,
                json={
                    "title": title,
                    "head": head,
                    "base": base,
                    "body": body,
                    "draft": draft,
                },
            )
            response.raise_for_status()
            return response.json()

    async def list_prs(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List pull requests.

        Args:
            owner: Repository owner
            repo: Repository name
            state: open, closed, or all
            per_page: Results per page

        Returns:
            List of pull request objects
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}/pulls",
                headers=self.headers,
                params={"state": state, "per_page": per_page},
            )
            response.raise_for_status()
            return response.json()

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """Get pull request details.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number

        Returns:
            Pull request object
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def merge_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_title: str = "",
        commit_message: str = "",
        merge_method: str = "merge",
    ) -> dict[str, Any]:
        """Merge a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            commit_title: Title for merge commit
            commit_message: Message for merge commit
            merge_method: merge, squash, or rebase

        Returns:
            Merge result object
        """
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.api_base}/repos/{owner}/{repo}/pulls/{pr_number}/merge",
                headers=self.headers,
                json={
                    "commit_title": commit_title,
                    "commit_message": commit_message,
                    "merge_method": merge_method,
                },
            )
            response.raise_for_status()
            return response.json()

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an issue.

        Args:
            owner: Repository owner
            repo: Repository name
            title: Issue title
            body: Issue description
            labels: List of label names
            assignees: List of usernames to assign

        Returns:
            Issue object
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/repos/{owner}/{repo}/issues",
                headers=self.headers,
                json={
                    "title": title,
                    "body": body,
                    "labels": labels or [],
                    "assignees": assignees or [],
                },
            )
            response.raise_for_status()
            return response.json()

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List issues.

        Args:
            owner: Repository owner
            repo: Repository name
            state: open, closed, or all
            per_page: Results per page

        Returns:
            List of issue objects
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}/issues",
                headers=self.headers,
                params={"state": state, "per_page": per_page},
            )
            response.raise_for_status()
            return response.json()

    async def add_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        """Add comment to issue or PR.

        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue or PR number
            body: Comment text

        Returns:
            Comment object
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/repos/{owner}/{repo}/issues/{issue_number}/comments",
                headers=self.headers,
                json={"body": body},
            )
            response.raise_for_status()
            return response.json()

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = "main",
    ) -> dict[str, Any]:
        """Get file content from repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path
            ref: Branch, tag, or commit SHA

        Returns:
            Content object with base64 encoded content
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/repos/{owner}/{repo}/contents/{path}",
                headers=self.headers,
                params={"ref": ref},
            )
            response.raise_for_status()
            return response.json()
