"""GitHub API router - OAuth, repositories, files, PRs."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import os

from backend.integrations.github import GitHubOAuth, GitHubAPI, GitHubRepository

router = APIRouter(prefix="/api/github", tags=["github"])


class GitHubSetupRequest(BaseModel):
    token: str
    username: str


class CloneRepoRequest(BaseModel):
    owner: str
    repo: str
    token: str


class CreatePRRequest(BaseModel):
    owner: str
    repo: str
    token: str
    title: str
    body: str
    head: str
    base: str


class UpdateFileRequest(BaseModel):
    token: str
    content: str
    message: str
    branch: str = "main"


@router.get("/status")
async def github_status():
    """Get GitHub connection status."""
    token = os.getenv("GITHUB_TOKEN", "")
    username = os.getenv("GITHUB_USERNAME", "")

    # For development: allow working without GitHub
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"

    if dev_mode and not token:
        return {
            "connected": True,
            "username": "dev-user",
            "dev_mode": True
        }

    return {
        "connected": bool(token and username),
        "username": username if token else None
    }


@router.get("/oauth/authorize")
async def github_oauth_authorize():
    """Get GitHub OAuth authorization URL."""
    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    oauth = GitHubOAuth(
        client_id=client_id,
        client_secret=os.getenv("GITHUB_CLIENT_SECRET", ""),
        redirect_uri=os.getenv("GITHUB_REDIRECT_URI", "http://localhost:3000/api/github/callback")
    )

    auth_url, state = oauth.get_authorization_url()
    return {"url": auth_url, "state": state}


@router.post("/oauth/callback")
async def github_oauth_callback(request: Request):
    """Handle GitHub OAuth callback."""
    data = await request.json()
    code = data.get("code")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    oauth = GitHubOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=os.getenv("GITHUB_REDIRECT_URI", "http://localhost:3000/api/github/callback")
    )

    try:
        token_data = await oauth.exchange_code_for_token(code)
        access_token = token_data.get("access_token")

        if not access_token:
            raise ValueError("No access token in response")

        user = await oauth.get_user_info(access_token)

        # Save to environment
        os.environ["GITHUB_TOKEN"] = access_token
        os.environ["GITHUB_USERNAME"] = user.get("login", "")

        return {
            "success": True,
            "token": access_token,
            "user": user
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth failed: {str(e)}")


@router.get("/user")
async def get_github_user(token: str):
    """Get authenticated GitHub user info."""
    try:
        api = GitHubAPI(token)
        user = await api.get_user()
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to get user: {str(e)}")


@router.get("/repos")
async def list_github_repos(token: str):
    """List user's GitHub repositories."""
    try:
        api = GitHubAPI(token)
        repos = await api.list_repos()
        return repos
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to list repos: {str(e)}")


@router.post("/repos/clone")
async def clone_github_repo(request: CloneRepoRequest):
    """Clone a GitHub repository."""
    try:
        repo = GitHubRepository(
            owner=request.owner,
            repo=request.repo,
            token=request.token
        )

        local_path = await repo.clone()

        return {
            "success": True,
            "path": str(local_path),
            "owner": request.owner,
            "repo": request.repo
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to clone: {str(e)}")


@router.get("/repos/{owner}/{repo}/branches")
async def list_repo_branches(owner: str, repo: str, token: str):
    """List repository branches."""
    try:
        api = GitHubAPI(token)
        branches = await api.list_branches(owner, repo)
        return branches
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to list branches: {str(e)}")


@router.post("/repos/{owner}/{repo}/pr")
async def create_pull_request(owner: str, repo: str, request: CreatePRRequest):
    """Create a pull request."""
    try:
        api = GitHubAPI(request.token)
        pr = await api.create_pr(
            owner=owner,
            repo=repo,
            title=request.title,
            body=request.body,
            head=request.head,
            base=request.base
        )
        return pr
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create PR: {str(e)}")


@router.get("/repos/{owner}/{repo}/prs")
async def list_pull_requests(owner: str, repo: str, token: str, state: str = "open"):
    """List repository pull requests."""
    try:
        api = GitHubAPI(token)
        prs = await api.list_prs(owner, repo, state=state)
        return prs
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to list PRs: {str(e)}")


@router.get("/repos/{owner}/{repo}/contents")
async def get_repo_contents(owner: str, repo: str, token: str, path: str = ""):
    """Get repository contents at path."""
    try:
        api = GitHubAPI(token)
        contents = await api.get_contents(owner, repo, path)
        return contents
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get contents: {str(e)}")


@router.get("/repos/{owner}/{repo}/file")
async def get_repo_file(owner: str, repo: str, token: str, path: str, ref: str = "main"):
    """Get file content from repository."""
    try:
        api = GitHubAPI(token)
        content = await api.get_file(owner, repo, path, ref=ref)
        return {"content": content, "path": path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get file: {str(e)}")


@router.get("/repos/{owner}/{repo}/tree")
async def get_repo_tree(owner: str, repo: str, token: str, ref: str = "main"):
    """Get repository file tree."""
    try:
        api = GitHubAPI(token)
        tree = await api.get_tree(owner, repo, ref=ref)
        return tree
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get tree: {str(e)}")


@router.put("/repos/{owner}/{repo}/file")
async def update_repo_file(owner: str, repo: str, path: str, request: UpdateFileRequest):
    """Create or update a file in repository."""
    try:
        api = GitHubAPI(request.token)
        result = await api.update_file(
            owner=owner,
            repo=repo,
            path=path,
            content=request.content,
            message=request.message,
            branch=request.branch
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update file: {str(e)}")
