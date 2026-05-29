"""Workspace statistics API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, List, Dict, Any
import os

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class WorkspaceStats(BaseModel):
    """Workspace statistics."""
    total_files: int
    total_lines: int
    total_size_bytes: int
    file_types: Dict[str, int]
    largest_files: List[Dict[str, Any]]
    python_files: int
    test_files: int
    config_files: int


class FileInfo(BaseModel):
    """File information."""
    path: str
    size_bytes: int
    lines: int
    extension: str


class TreeNode(BaseModel):
    """File tree node."""
    name: str
    path: str
    type: str  # "file" or "directory"
    children: Optional[List['TreeNode']] = None
    size: Optional[int] = None
    extension: Optional[str] = None

    class Config:
        # Allow recursive models
        arbitrary_types_allowed = True


# Update forward references for recursive model
TreeNode.model_rebuild()


@router.get("/detect")
async def detect_workspace():
    """Auto-detect the current workspace directory.
    
    Checks in order:
    1. SHARROWKIN_WORKSPACE env var
    2. Current working directory (if it has .git or pyproject.toml or package.json)
    3. Parent of the running process
    """
    import sys

    # 1. Environment variable
    env_path = os.environ.get("SHARROWKIN_WORKSPACE")
    if env_path and Path(env_path).exists():
        return {"path": env_path, "source": "env"}

    # 2. Current working directory
    cwd = Path.cwd()
    project_markers = {'.git', 'pyproject.toml', 'package.json', 'Cargo.toml', 'go.mod'}
    if any((cwd / marker).exists() for marker in project_markers):
        return {"path": str(cwd), "source": "cwd"}

    # 3. Walk up from cwd to find a project root
    for parent in cwd.parents:
        if any((parent / marker).exists() for marker in project_markers):
            return {"path": str(parent), "source": "parent"}

    # 4. Fallback to cwd anyway
    return {"path": str(cwd), "source": "fallback"}


@router.get("/tree")
async def get_workspace_tree(path: str):
    """Get workspace file tree."""
    workspace_path = Path(path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    def build_tree(dir_path: Path, max_depth: int = 5, current_depth: int = 0) -> Dict[str, Any]:
        """Recursively build file tree as dict."""
        if current_depth >= max_depth:
            return None

        name = dir_path.name or str(dir_path)
        # Use relative path as id for uniqueness
        try:
            rel_path = str(dir_path.relative_to(workspace_path)).replace("\\", "/")
        except ValueError:
            rel_path = str(dir_path).replace("\\", "/")

        if dir_path.is_file():
            return {
                "id": rel_path or name,
                "name": name,
                "path": rel_path,
                "type": "file",
                "size": dir_path.stat().st_size,
                "extension": dir_path.suffix or None,
                "children": None
            }

        # Directory
        children = []
        try:
            entries = sorted(dir_path.iterdir())
            # Sort: folders first, then files, alphabetically within each group
            folders = sorted([e for e in entries if e.is_dir()], key=lambda x: x.name.lower())
            files = sorted([e for e in entries if e.is_file()], key=lambda x: x.name.lower())
            for item in folders + files:
                # Skip common ignore directories
                if item.name in {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                                '.pytest_cache', '.mypy_cache', 'dist', 'build', '.next',
                                '.sharrowkin', '.codegraph', '.kiro'}:
                    continue

                child = build_tree(item, max_depth, current_depth + 1)
                if child:
                    children.append(child)
        except PermissionError:
            pass

        return {
            "id": rel_path or name,
            "name": name,
            "path": rel_path,
            "type": "folder",
            "children": children if children else None,
            "size": None,
            "extension": None
        }

    tree = build_tree(workspace_path)
    return {"tree": tree}


@router.get("/stats", response_model=WorkspaceStats)
async def get_workspace_stats(workspace: Optional[str] = None):
    """Get workspace statistics."""
    if not workspace:
        workspace = "/tmp/sharrowkin-workspace/repos/sharrowkin-backend"
    
    workspace_path = Path(workspace)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    total_files = 0
    total_lines = 0
    total_size = 0
    file_types = {}
    files_info = []
    python_files = 0
    test_files = 0
    config_files = 0
    
    # Scan workspace
    for root, dirs, files in os.walk(workspace_path):
        # Skip common ignore directories
        dirs[:] = [d for d in dirs if d not in {
            '.git', '__pycache__', 'node_modules', '.venv', 'venv',
            '.pytest_cache', '.mypy_cache', 'dist', 'build'
        }]
        
        for file in files:
            file_path = Path(root) / file
            try:
                size = file_path.stat().st_size
                ext = file_path.suffix or 'no_extension'
                
                # Count file types
                file_types[ext] = file_types.get(ext, 0) + 1
                
                # Count lines for text files
                lines = 0
                if ext in {'.py', '.js', '.ts', '.jsx', '.tsx', '.md', '.txt', '.yaml', '.yml', '.json', '.toml'}:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = sum(1 for _ in f)
                    except:
                        pass
                
                total_files += 1
                total_lines += lines
                total_size += size
                
                # Track Python files
                if ext == '.py':
                    python_files += 1
                    if 'test_' in file or '_test.py' in file:
                        test_files += 1
                
                # Track config files
                if file in {'pyproject.toml', 'package.json', 'tsconfig.json', 'setup.py', 'requirements.txt'}:
                    config_files += 1
                
                files_info.append({
                    'path': str(file_path.relative_to(workspace_path)),
                    'size': size,
                    'lines': lines,
                    'ext': ext
                })
            except Exception:
                continue
    
    # Get largest files
    largest_files = sorted(files_info, key=lambda x: x['size'], reverse=True)[:10]
    
    return WorkspaceStats(
        total_files=total_files,
        total_lines=total_lines,
        total_size_bytes=total_size,
        file_types=file_types,
        largest_files=largest_files,
        python_files=python_files,
        test_files=test_files,
        config_files=config_files
    )


# ─── File read endpoint ──────────────────────────────────────────────────────


@router.get("/file")
async def get_workspace_file(workspace: str, path: str):
    """Read a file's content from the workspace."""
    workspace_path = Path(workspace)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Resolve relative path against workspace
    file_path = workspace_path / path
    # Security: ensure the resolved path is inside the workspace
    try:
        file_path = file_path.resolve()
        workspace_path.resolve()
        if not str(file_path).startswith(str(workspace_path.resolve())):
            raise HTTPException(status_code=403, detail="Path traversal not allowed")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Read with size limit (5 MB)
    if file_path.stat().st_size > 5 * 1024 * 1024:
        return {"content": "[File too large to display (>5 MB)]", "path": path, "truncated": True}

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    return {"content": content, "path": path, "lines": content.count("\n") + 1}


# ─── File write endpoint ─────────────────────────────────────────────────────


class FileWriteRequest(BaseModel):
    workspace: str
    path: str
    content: str


@router.put("/file")
async def write_workspace_file(req: FileWriteRequest):
    """Write content to a file in the workspace."""
    workspace_path = Path(req.workspace)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    file_path = workspace_path / req.path
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(workspace_path.resolve())):
            raise HTTPException(status_code=403, detail="Path traversal not allowed")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(req.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")

    return {"success": True, "path": req.path}


# ─── Search endpoint ─────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    workspace: str
    query: str
    max_results: int = 30


@router.post("/search")
async def search_workspace(req: SearchRequest):
    """Search for text in workspace files."""
    workspace_path = Path(req.workspace)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    query_lower = req.query.lower()
    results = []

    skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                 '.pytest_cache', '.mypy_cache', 'dist', 'build', '.next',
                 '.sharrowkin', '.codegraph', '.kiro'}

    text_extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.md',
                       '.txt', '.yaml', '.yml', '.toml', '.css', '.html',
                       '.rs', '.go', '.java', '.c', '.cpp', '.h', '.sh'}

    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            if len(results) >= req.max_results:
                break

            file_path = Path(root) / file
            if file_path.suffix.lower() not in text_extensions:
                continue
            if file_path.stat().st_size > 1 * 1024 * 1024:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                for line_no, line in enumerate(content.splitlines(), 1):
                    if query_lower in line.lower():
                        rel_path = str(file_path.relative_to(workspace_path)).replace("\\", "/")
                        results.append({
                            "file": rel_path,
                            "line": line_no,
                            "match": line.strip()[:200],
                        })
                        if len(results) >= req.max_results:
                            break
            except Exception:
                continue

    return {"results": results, "total": len(results)}


@router.get("/file")
async def get_workspace_file(workspace: str, path: str):
    """Read a file from the workspace."""
    workspace_path = Path(workspace)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Resolve the file path (relative or absolute)
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = workspace_path / path

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Security: ensure file is within workspace
    try:
        file_path.resolve().relative_to(workspace_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: file outside workspace")

    # Read file content
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    return {
        "path": path,
        "content": content,
        "size": file_path.stat().st_size,
        "lines": content.count("\n") + 1,
    }


@router.put("/file")
async def save_workspace_file(body: dict):
    """Save content to a file in the workspace."""
    workspace = body.get("workspace", "")
    path = body.get("path", "")
    content = body.get("content", "")

    if not workspace or not path:
        raise HTTPException(status_code=400, detail="Missing workspace or path")

    workspace_path = Path(workspace)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = workspace_path / path

    # Security: ensure file is within workspace
    try:
        file_path.resolve().relative_to(workspace_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: file outside workspace")

    try:
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    return {"success": True, "path": path}


class SearchRequest(BaseModel):
    workspace: str
    query: str
    max_results: int = 30


@router.post("/search")
async def search_workspace(body: SearchRequest):
    """Search for text in workspace files."""
    workspace_path = Path(body.workspace)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    results = []
    query_lower = body.query.lower()

    # Walk through files and search
    skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                 '.pytest_cache', '.mypy_cache', 'dist', 'build', '.next',
                 '.sharrowkin', '.codegraph', '.kiro'}
    text_extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.md',
                       '.txt', '.yaml', '.yml', '.toml', '.css', '.html',
                       '.rs', '.go', '.java', '.c', '.cpp', '.h'}

    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            if len(results) >= body.max_results:
                break

            file_path = Path(root) / file
            if file_path.suffix.lower() not in text_extensions:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if query_lower in line.lower():
                        rel_path = str(file_path.relative_to(workspace_path)).replace("\\", "/")
                        results.append({
                            "file": rel_path,
                            "line": line_num,
                            "match": line.strip()[:200],
                        })
                        if len(results) >= body.max_results:
                            break
            except Exception:
                continue

    return {"results": results, "total": len(results)}
