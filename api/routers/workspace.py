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