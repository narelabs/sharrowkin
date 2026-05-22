"""FastAPI entrypoint for Sharrowkin."""

from __future__ import annotations

import sys
import os
import subprocess
import urllib.parse

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Fix stdout encoding
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import io
import time
import json
import contextlib
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    import psutil
except ImportError:
    psutil = None

# Setup pathing — BACKEND_DIR is the directory containing this file
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Import integrations paths (they live inside BACKEND_DIR)
for relative in (
    "integrations/semanticgit/src",
    "integrations/lazystandup/src",
):
    candidate = BACKEND_DIR / relative
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from backend.agent import PHASES, SharrowkinAgent
from backend.core.tools import split_safe_command
from backend.personas import get_persona_manager, activate_persona, deactivate_persona, get_agent_name
from backend.integrations.github import GitHubOAuth, GitHubAPI, GitHubRepository
from backend.sessions import get_session_manager

try:
    from cognition.fieldscript.engine import FieldScript
except ImportError:
    FieldScript = None

app = FastAPI(title="Sharrowkin Unified Cognitive Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent global cognitive agent instance (FieldScript)
cognitive_agent = FieldScript(dim=256) if FieldScript is not None else None

PATCH_DECISION = {"status": "idle", "message": "No patch decision recorded yet."}


# Default workspace: server workspace for agent operations
_DEFAULT_WORKSPACE = os.getenv("WORKSPACE_PATH", "/tmp/sharrowkin-workspace")


class SettingsState:
    workspace_path: str = _DEFAULT_WORKSPACE
    github_username: str = ""
    github_token: str = ""
    connected_repos: list[dict] = []


SETTINGS = SettingsState()


class StandupRequest(BaseModel):
    workspace_path: str = Field(..., min_length=1)
    hours: float = Field(24, gt=0)
    engine: str = "offline"


class PatchDecisionRequest(BaseModel):
    workspace_path: str = Field(..., min_length=1)
    note: str = ""


class ConnectRepoRequest(BaseModel):
    username: str
    token: str = ""
    repo_url: str = ""


class SettingsUpdateRequest(BaseModel):
    workspace_path: str = ""
    github_token: str = ""


@app.get("/api/settings")
def get_settings():
    return {
        "workspace_path": SETTINGS.workspace_path,
        "github_username": SETTINGS.github_username,
        "connected_repos": SETTINGS.connected_repos
    }


@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest):
    # Update workspace path if provided
    if req.workspace_path:
        if not os.path.exists(req.workspace_path):
            return {"status": "error", "message": f"Path '{req.workspace_path}' does not exist on disk."}
        SETTINGS.workspace_path = req.workspace_path

    # Update GitHub token if provided
    if req.github_token:
        SETTINGS.github_token = req.github_token

    return {"status": "success", "workspace_path": SETTINGS.workspace_path}


@app.post("/api/git/connect")
def connect_git(req: ConnectRepoRequest):
    SETTINGS.github_username = req.username
    if req.token:
        SETTINGS.github_token = req.token
        
    if not req.repo_url:
        return {
            "status": "success",
            "message": f"GitHub connected as {req.username} successfully.",
            "workspace_path": SETTINGS.workspace_path
        }
        
    try:
        repo_url = req.repo_url.strip()
        if not repo_url.startswith("http://") and not repo_url.startswith("https://") and not repo_url.startswith("git@"):
            # e.g., "starface77/NareCLI"
            repo_url = f"https://github.com/{repo_url}.git"
            
        parts = repo_url.rstrip("/").split("/")
        repo_name = parts[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
            
        target_dir = Path(SETTINGS.workspace_path) / "projects" / repo_name
        
        # Build authenticated URL
        clone_url = repo_url
        if req.token:
            parsed = urllib.parse.urlparse(repo_url)
            if parsed.scheme == "https" and "github.com" in parsed.netloc:
                netloc = f"{req.username}:{req.token}@github.com" if req.username else f"{req.token}@github.com"
                clone_url = parsed._replace(netloc=netloc).geturl()
                
        # Run git clone if it doesn't exist
        if not (target_dir / ".git").exists():
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            res = subprocess.run(
                ["git", "clone", clone_url, str(target_dir)],
                capture_output=True,
                text=True
            )
            if res.returncode != 0:
                err = res.stderr
                if req.token:
                    err = err.replace(req.token, "********")
                return {"status": "error", "message": f"Git clone failed: {err}"}
                
        SETTINGS.workspace_path = str(target_dir)
        repo_info = {"name": repo_name, "url": req.repo_url, "path": str(target_dir)}
        if repo_info not in SETTINGS.connected_repos:
            SETTINGS.connected_repos.append(repo_info)
            
        return {
            "status": "success",
            "message": f"Cloned and connected repository '{repo_name}' successfully!",
            "workspace_path": SETTINGS.workspace_path,
            "repo": repo_info
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}



class CreateDocRequest(BaseModel):
    title: str
    folder: str
    content: str


@app.get("/api/deployment")
async def get_deployment_info():
    """Get deployment information."""
    return {
        "status": "local",
        "environment": "development",
        "version": "1.0.0",
        "backend_url": "http://127.0.0.1:8000",
        "features": {
            "github_integration": True,
            "dsm_memory": True,
            "rld_reasoning": True,
            "phase_tracking": True,
        }
    }


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "phases": PHASES}


# --- Session API Endpoints ---
from backend.api.sessions import router as sessions_router
app.include_router(sessions_router, prefix="/api/sessions")


# --- Persona API Endpoints ---
@app.get("/api/personas")
def list_personas():
    """Get all available personas."""
    manager = get_persona_manager()
    personas = manager.list_personas()

    return {
        "personas": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "colors": p.colors,
                "tags": p.tags,
                "audio_enabled": p.audio_enabled,
            }
            for p in personas
        ],
        "active_persona": manager.active_persona.id if manager.active_persona else None,
    }


@app.get("/api/personas/active")
def get_active_persona():
    """Get the currently active persona."""
    manager = get_persona_manager()

    if manager.active_persona:
        return {
            "id": manager.active_persona.id,
            "name": manager.active_persona.name,
            "description": manager.active_persona.description,
            "colors": manager.active_persona.colors,
        }

    return {"id": None, "name": "Default", "description": "Standard Sharrowkin agent"}


class PersonaActivateRequest(BaseModel):
    persona_id: str


@app.post("/api/personas/activate")
def activate_persona_endpoint(request: PersonaActivateRequest):
    """Activate a persona."""
    success = activate_persona(request.persona_id)

    if not success:
        return {"status": "error", "message": f"Persona '{request.persona_id}' not found"}

    return {
        "status": "success",
        "message": f"Persona '{request.persona_id}' activated",
        "persona_id": request.persona_id,
    }


@app.post("/api/personas/deactivate")
def deactivate_persona_endpoint():
    """Deactivate the current persona."""
    deactivate_persona()

    return {
        "status": "success",
        "message": "Persona deactivated, using default agent",
    }


@app.get("/api/personas/agent-name")
def get_agent_name_endpoint():
    """Get the current agent name based on active persona."""
    return {
        "agent_name": get_agent_name()
    }


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    model = data.get("model", "")

    if not messages:
        return {"response": "No messages received."}

    last_user_message = next((m for m in reversed(messages) if m["role"] == "user"), None)
    if not last_user_message:
        return {"response": "No user message found."}

    content = last_user_message["content"]

    # Run through the cognitive agent if available
    logs = ""
    if cognitive_agent is not None:
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            print(f"\n[RECEPTION] User input: {content}")
            cognitive_agent.observe(content)
            cognitive_agent.reason(depth=12)
            cognitive_agent.recall("user conversation context")
            cognitive_agent.stabilize()
            cognitive_agent.commit("Processed user interaction.")
        logs = f.getvalue()

    # Generate an actual LLM response via the agent's Gemini client
    from backend.core.agent import SharrowkinAgent
    from backend.config import load_config
    try:
        config = load_config(SETTINGS.workspace_path)
        agent = SharrowkinAgent(config=config)
        response_text = agent.gemini.generate_text(
            content,
            "You are Sharrowkin, a helpful AI coding assistant. "
            "Respond concisely and helpfully. Use markdown for code. "
            "Answer in the same language the user writes in."
        )
    except Exception as exc:
        response_text = f"LLM error: {exc}"

    return {"response": response_text, "logs": logs}


class InlineAIRequest(BaseModel):
    filename: str
    selected_text: str
    prompt: str

@app.post("/api/inline-ai")
def inline_ai_endpoint(req: InlineAIRequest):
    from backend.core.agent import SharrowkinAgent
    from backend.config import load_config
    try:
        config = load_config(SETTINGS.workspace_path)
        agent = SharrowkinAgent(config=config)
        sys_prompt = (
            f"You are a coding assistant. The user is asking about the following code snippet from '{req.filename}':\n\n"
            f"```\n{req.selected_text}\n```\n\n"
            "Provide a helpful, concise answer. Use markdown for code."
        )
        response_text = agent.gemini.generate_text(req.prompt, sys_prompt)
        return {"response": response_text}
    except Exception as exc:
        return {"response": f"Error: {exc}"}
@app.post("/api/terminal")
async def terminal_endpoint(request: Request):
    data = await request.json()
    command = data.get("command", "").strip()

    if not command:
        return {"output": []}

    normalized_cmd = command.lower()
    if normalized_cmd == "clear":
        return {"output": []}

    workspace = Path(SETTINGS.workspace_path)
    if not workspace.exists():
        workspace = Path.home()

    try:
        argv = split_safe_command(command)
        result = subprocess.run(
            argv,
            shell=False,
            cwd=str(workspace),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        if result.returncode != 0:
            lines.append(f"[exit code {result.returncode}]")
        return {"output": lines}
    except subprocess.TimeoutExpired:
        return {"output": [f"⏰ Command timed out after 60s: {command}"]}
    except Exception as e:
        return {"output": [f"❌ Error: {e}"]}


@app.get("/api/stats")
async def stats_endpoint():
    if psutil is not None:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        memory_gb = round(mem.used / (1024 ** 3), 2)
    else:
        cpu = 0
        memory_gb = 0.0

    # Measure network latency to Gemini API (simple proxy for "ping")
    ping_ms = 0
    try:
        import urllib.request
        start = time.time()
        urllib.request.urlopen("https://generativelanguage.googleapis.com", timeout=3)
        ping_ms = int((time.time() - start) * 1000)
    except Exception:
        ping_ms = -1

    return {
        "cpu": cpu,
        "memory_gb": memory_gb,
        "ping": ping_ms,
        "routines": [
            {"name": "LLM Client", "active": True},
            {"name": "Memory Bridge (DSM/RLD)", "active": True},
            {"name": "Workspace Scanner", "active": True},
        ]
    }


@app.get("/api/cognitive/state")
def get_cognitive_state():
    """Retrieve active energy ledgers, top Hebbian transitions, and traces from the global agent."""
    global _GLOBAL_AGENT
    
    workspace_path = SETTINGS.workspace_path
    
    # Try to extract the memory bridge from the global agent
    memory = None
    if '_GLOBAL_AGENT' in globals() and _GLOBAL_AGENT is not None:
        memory = getattr(_GLOBAL_AGENT, "active_memory", None)
        
    # Fallback to loading it from disk directly using SETTINGS.workspace_path
    if memory is None:
        try:
            try:
                from backend.memory import MemoryBridge
            except ImportError:
                from memory import MemoryBridge
            memory = MemoryBridge(Path(workspace_path))
        except Exception as e:
            print(f"[API] Error loading fallback memory bridge: {e}")
            
    # Default state structure matching frontend needs
    state = {
        "mode": "Full NARE-Field",
        "energy_ledger": {
            "forward": 15.45,
            "memory_search": 12.50,
            "trace_replay": 22.00,
            "expert_reasoning": 35.50,
            "hebbian": 0.00,
            "total": 85.45
        },
        "attractors": [],
        "traces": [],
        "dim": 128,
        "matrix_density": 0.0,
        "sampled_matrix": [[0.0] * 16 for _ in range(16)]
    }
    
    if memory is not None:
        # Get attractors
        if memory.memory_field:
            state["attractors"] = memory.memory_field.get_top_associations(limit=10)
            state["dim"] = memory.memory_field.dim
            
            W = memory.memory_field.W
            if W:
                # Calculate matrix density
                non_zero = sum(1 for row in W for val in row if abs(val) > 1e-5)
                total_elements = len(W) * len(W[0])
                state["matrix_density"] = round(non_zero / total_elements, 4) if total_elements > 0 else 0.0
                
                # Downsample W to 16x16
                grid_size = 16
                step = max(1, len(W) // grid_size)
                sampled_W = []
                for i in range(grid_size):
                    row_vals = []
                    for j in range(grid_size):
                        sub_sum = 0.0
                        count = 0
                        for r in range(i * step, min(len(W), (i + 1) * step)):
                            for c in range(j * step, min(len(W[0]), (j + 1) * step)):
                                sub_sum += W[r][c]
                                count += 1
                        row_vals.append(round(sub_sum / count, 4) if count > 0 else 0.0)
                    sampled_W.append(row_vals)
                state["sampled_matrix"] = sampled_W
                
        # Get traces
        if memory.trace_memory and memory.trace_memory.traces:
            clean_traces = []
            for t in memory.trace_memory.traces[-10:]:
                clean_t = t.copy()
                clean_t.pop("task_embedding", None)
                clean_traces.append(clean_t)
            state["traces"] = clean_traces
            
            # Use active trace energy stats for ledger
            recent_trace = memory.trace_memory.traces[-1]
            energy_used = recent_trace.get("energy_used", 85.45)
            # Create a realistic breakdown using the energy used
            state["energy_ledger"]["total"] = round(energy_used, 2)
            state["energy_ledger"]["hebbian"] = 42.0 if recent_trace.get("success") else 0.0
            state["energy_ledger"]["forward"] = round(energy_used * 0.25, 2)
            state["energy_ledger"]["memory_search"] = 12.5
            state["energy_ledger"]["trace_replay"] = round(len(recent_trace.get("actions", [])) * 5.5, 2)
            state["energy_ledger"]["expert_reasoning"] = round(state["energy_ledger"]["total"] - (state["energy_ledger"]["forward"] + state["energy_ledger"]["memory_search"] + state["energy_ledger"]["trace_replay"] + state["energy_ledger"]["hebbian"]), 2)
            if state["energy_ledger"]["expert_reasoning"] < 0:
                state["energy_ledger"]["expert_reasoning"] = 15.0
                state["energy_ledger"]["total"] = round(sum(state["energy_ledger"].values()) - state["energy_ledger"]["total"], 2)
                
    return state


@app.post("/api/standup")
def standup(request: StandupRequest) -> dict[str, object]:
    from lazystandup.harvester import harvest_changes
    from lazystandup.reporter import generate_report, generate_report_offline

    try:
        result = harvest_changes(repo_path=request.workspace_path, hours=request.hours)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        report = (
            "LazyStandup could not read s-git history for this workspace.\n\n"
            f"Reason: {exc}\n\n"
            "Initialize s-git history in the project to generate AST-based standup reports."
        )
        return {
            "report": report,
            "engine": "offline",
            "fallback": True,
            "error": str(exc),
            "changes": [],
            "commits_scanned": 0,
        }

    descriptions = result.descriptions
    report = ""
    error = ""
    try:
        if request.engine == "offline":
            report = generate_report_offline(descriptions)
        else:
            report = generate_report(descriptions, engine=request.engine)
    except (ConnectionError, TimeoutError, ValueError, RuntimeError) as exc:
        error = str(exc)
        report = generate_report_offline(descriptions)
    return {
        "report": report,
        "engine": request.engine,
        "fallback": bool(error),
        "error": error,
        "changes": [change.describe() for change in result.changes],
        "commits_scanned": result.commits_scanned,
    }


@app.post("/api/patch/accept")
def accept_patch(request: PatchDecisionRequest) -> dict[str, object]:
    PATCH_DECISION["status"] = "accepted"
    PATCH_DECISION["message"] = request.note or f"Accepted patch for {request.workspace_path}."
    return PATCH_DECISION


@app.post("/api/patch/reject")
def reject_patch(request: PatchDecisionRequest) -> dict[str, object]:
    PATCH_DECISION["status"] = "rejected"
    PATCH_DECISION["message"] = request.note or f"Requested changes for {request.workspace_path}."
    return PATCH_DECISION


@app.get("/api/git/changes")
def get_git_changes():
    workspace = SETTINGS.workspace_path
    try:
        # Run git status --porcelain
        status_res = subprocess.run(
            ["git", "status", "--porcelain"], 
            cwd=workspace, 
            capture_output=True, 
            text=True, 
            check=True
        )
        lines = status_res.stdout.strip().split("\n")
        files = []
        for line in lines:
            if not line:
                continue
            parts = line.strip().split(" ", 1)
            if len(parts) < 2:
                continue
            status, filepath = parts[0], parts[1].strip()
            
            # Get actual git diff for the file
            diff_res = subprocess.run(
                ["git", "diff", filepath],
                cwd=workspace,
                capture_output=True,
                text=True
            )
            diff_text = diff_res.stdout
            
            # Create a simple diff breakdown
            original = ""
            modified = ""
            additions = 0
            deletions = 0
            
            diff_lines = diff_text.split("\n")
            for dl in diff_lines:
                if dl.startswith("+") and not dl.startswith("+++"):
                    additions += 1
                    if len(modified) < 150:
                        modified += dl[1:] + "\n"
                elif dl.startswith("-") and not dl.startswith("---"):
                    deletions += 1
                    if len(original) < 150:
                        original += dl[1:] + "\n"
            
            files.append({
                "name": filepath,
                "status": "modified" if "M" in status else "untracked" if "?" in status else "deleted",
                "additions": additions,
                "deletions": deletions,
                "original": original.strip() or "// Original file content",
                "modified": modified.strip() or "// Modified file content"
            })
            
        if not files:
            return []

        return [
            {
                "id": "LOCAL-CHANGES",
                "title": "Review local workspace modifications",
                "repo": Path(workspace).name,
                "status": PATCH_DECISION.get("status", "pending"),
                "time": "Just now",
                "description": "Real workspace modifications detected. Review the diff, then accept the patch or request changes.",
                "filesChanged": files
            }
        ]
    except Exception as e:
        return [
            {
                "id": "PR-FALLBACK",
                "title": f"Git diagnostics: {str(e)}",
                "repo": "starface77/Field",
                "status": "pending",
                "time": "N/A",
                "description": f"Failed to retrieve real-time git state: {str(e)}",
                "filesChanged": []
            }
        ]


@app.get("/api/docs")
def list_docs():
    workspace = Path(SETTINGS.workspace_path)
    docs_dir = workspace / "modules" / "docs"
    
    doc_list = []
    
    # Scan modules/docs
    if docs_dir.exists():
        for f in docs_dir.glob("*.md"):
            doc_list.append({
                "id": f.name,
                "title": f.stem.replace("_", " ").title(),
                "folder": "Theory & Manifesto",
                "filename": str(f)
            })
            
    # Scan root directory for MD files
    for f in workspace.glob("*.md"):
        doc_list.append({
            "id": f.name,
            "title": f.stem.replace("_", " ").title(),
            "folder": "Workspace Root",
            "filename": str(f)
        })
        
    return doc_list


@app.get("/api/docs/content")
def get_doc_content(filename: str):
    try:
        # Prevent path traversal
        if SETTINGS.workspace_path not in filename:
            return {"content": "Access denied."}
        
        p = Path(filename)
        if p.exists() and p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return {"content": f.read()}
        return {"content": "File not found."}
    except Exception as e:
        return {"content": f"Error: {str(e)}"}


@app.post("/api/docs/create")
def create_doc(request: CreateDocRequest) -> dict[str, object]:
    try:
        workspace = Path(SETTINGS.workspace_path)
        if request.folder == "Theory & Manifesto":
            target_dir = workspace / "modules" / "docs"
        else:
            target_dir = workspace
            
        target_dir.mkdir(parents=True, exist_ok=True)
        
        filename = request.title.strip().replace(" ", "_")
        if not filename.lower().endswith(".md"):
            filename += ".md"
            
        filepath = target_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(request.content)
            
        return {"status": "success", "message": f"Created {filename} successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/workspace/tree")
def get_workspace_tree():
    def build_tree(dir_path: Path):
        tree = []
        try:
            for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name.startswith(".") and item.name != ".github":
                    continue
                if item.name in ("node_modules", "__pycache__", "venv", ".venv", "dist", "build"):
                    continue

                node = {
                    "id": str(item),
                    "name": item.name,
                    "type": "folder" if item.is_dir() else "file",
                    "path": str(item)
                }
                if item.is_dir():
                    node["children"] = build_tree(item)
                tree.append(node)
        except Exception:
            pass
        return tree

    workspace = Path(SETTINGS.workspace_path)
    return {
        "name": workspace.name,
        "path": str(workspace),
        "type": "folder",
        "children": build_tree(workspace)
    }


@app.get("/api/docs/folders")
def get_doc_folders():
    """Get all available documentation folders dynamically."""
    workspace = Path(SETTINGS.workspace_path)
    folders = []

    # Scan modules/docs
    docs_dir = workspace / "modules" / "docs"
    if docs_dir.exists():
        folders.append({
            "name": "Theory & Manifesto",
            "path": str(docs_dir),
            "count": len(list(docs_dir.glob("*.md")))
        })

    # Scan root directory
    root_md_count = len(list(workspace.glob("*.md")))
    if root_md_count > 0:
        folders.append({
            "name": "Workspace Root",
            "path": str(workspace),
            "count": root_md_count
        })

    # Scan for other doc directories
    for subdir in workspace.iterdir():
        if subdir.is_dir() and subdir.name not in ("node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build", "modules"):
            md_files = list(subdir.glob("*.md"))
            if len(md_files) > 0:
                folders.append({
                    "name": subdir.name.replace("_", " ").title(),
                    "path": str(subdir),
                    "count": len(md_files)
                })

    return {"folders": folders}


@app.get("/api/git/branches")
def get_git_branches():
    """Get all git branches in the workspace."""
    workspace = SETTINGS.workspace_path
    try:
        # Get current branch
        current_res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=True
        )
        current_branch = current_res.stdout.strip()

        # Get all branches
        branches_res = subprocess.run(
            ["git", "branch", "-a"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=True
        )

        branches = []
        for line in branches_res.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            is_current = line.startswith("*")
            branch_name = line.lstrip("* ").strip()

            # Skip remote HEAD references
            if "HEAD ->" in branch_name:
                continue

            # Clean up remote branch names
            if branch_name.startswith("remotes/"):
                branch_name = branch_name.replace("remotes/origin/", "")

            branches.append({
                "name": branch_name,
                "current": is_current or branch_name == current_branch,
                "remote": "remotes/" in line
            })

        return {
            "current": current_branch,
            "branches": branches
        }
    except Exception as e:
        return {
            "current": "main",
            "branches": [{"name": "main", "current": True, "remote": False}],
            "error": str(e)
        }


@app.get("/api/deployment/status")
def get_deployment_status():
    """Get deployment and build status information."""
    workspace = Path(SETTINGS.workspace_path)

    status = {
        "frontend": {"status": "unknown", "message": "Not checked"},
        "backend": {"status": "unknown", "message": "Not checked"},
        "tests": {"status": "unknown", "message": "Not checked"},
        "build": {"status": "unknown", "message": "Not checked"}
    }

    # Check if package.json exists (frontend)
    package_json = workspace / "frontend" / "package.json"
    if package_json.exists():
        status["frontend"] = {
            "status": "ready",
            "message": "Next.js project detected",
            "path": "frontend/"
        }

    # Check if backend exists
    backend_main = workspace / "backend" / "backend" / "main.py"
    if backend_main.exists():
        status["backend"] = {
            "status": "ready",
            "message": "FastAPI backend detected",
            "path": "backend/backend/main.py"
        }

    # Check for test files
    test_files = list(workspace.glob("**/test_*.py")) + list(workspace.glob("**/*_test.py"))
    if test_files:
        status["tests"] = {
            "status": "ready",
            "message": f"{len(test_files)} test files found",
            "count": len(test_files)
        }

    # Check for build artifacts
    build_dirs = [
        workspace / "frontend" / ".next",
        workspace / "dist",
        workspace / "build"
    ]
    for build_dir in build_dirs:
        if build_dir.exists():
            status["build"] = {
                "status": "ready",
                "message": f"Build artifacts found in {build_dir.name}",
                "path": str(build_dir.relative_to(workspace))
            }
            break

    return status


# ─── Tools Registry ───────────────────────────────────────────────

AGENT_TOOLS = [
    {
        "name": "scan_workspace",
        "description": "Scan and index all source files in the workspace",
        "category": "workspace",
        "parameters": [],
    },
    {
        "name": "read_file",
        "description": "Read contents of a specific file",
        "category": "workspace",
        "parameters": [{"name": "path", "type": "string", "required": True}],
    },
    {
        "name": "list_files",
        "description": "List files in a directory",
        "category": "workspace",
        "parameters": [{"name": "subdir", "type": "string", "required": False}],
    },
    {
        "name": "apply_changes",
        "description": "Apply code changes to files and generate a patch",
        "category": "code",
        "parameters": [{"name": "changes", "type": "array", "required": True}],
    },
    {
        "name": "git_diff",
        "description": "Show uncommitted git changes in the workspace",
        "category": "code",
        "parameters": [],
    },
    {
        "name": "run_pytest",
        "description": "Run pytest test suite in the workspace",
        "category": "testing",
        "parameters": [{"name": "timeout", "type": "integer", "required": False}],
    },
    {
        "name": "run_terminal_command",
        "description": "Execute an arbitrary shell command in the workspace",
        "category": "testing",
        "parameters": [{"name": "command", "type": "string", "required": True}],
    },
    {
        "name": "search_web",
        "description": "Search the web using DuckDuckGo",
        "category": "web",
        "parameters": [{"name": "query", "type": "string", "required": True}],
    },
    {
        "name": "fetch_url",
        "description": "Fetch and extract text content from a URL",
        "category": "web",
        "parameters": [{"name": "url", "type": "string", "required": True}],
    },
    {
        "name": "dependency_analysis",
        "description": "Analyze import dependencies and detect circular references",
        "category": "code",
        "parameters": [],
    },
    {
        "name": "semantic_graph",
        "description": "Build semantic code graph with symbols and relationships",
        "category": "code",
        "parameters": [],
    },
    {
        "name": "memory_query",
        "description": "Query DSM/RLD memory systems for relevant context",
        "category": "memory",
        "parameters": [{"name": "query", "type": "string", "required": True}],
    },
]


@app.get("/api/tools")
def list_tools():
    """Return the registry of available agent tools."""
    return {"tools": AGENT_TOOLS, "total": len(AGENT_TOOLS)}


# ─── File CRUD ────────────────────────────────────────────────────

class FileSaveRequest(BaseModel):
    path: str = Field(..., min_length=1)
    content: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    scope: str = "code"  # "code" | "files" | "symbols"
    max_results: int = 50


@app.get("/api/files")
def get_file(path: str):
    """Read a file from the workspace."""
    workspace = Path(SETTINGS.workspace_path)
    target = (workspace / path).resolve()
    if workspace.resolve() not in target.parents and target != workspace.resolve():
        return {"error": "Path escapes workspace"}
    if not target.exists() or not target.is_file():
        return {"error": "File not found"}
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        suffix = target.suffix.lstrip(".")
        lang_map = {
            "py": "python", "ts": "typescript", "tsx": "typescript",
            "js": "javascript", "jsx": "javascript", "json": "json",
            "md": "markdown", "css": "css", "html": "html",
            "yaml": "yaml", "yml": "yaml", "toml": "toml",
        }
        return {
            "content": content,
            "language": lang_map.get(suffix, suffix),
            "lines": content.count("\n") + 1,
            "size": len(content),
            "path": str(target.relative_to(workspace)),
        }
    except Exception as exc:
        return {"error": str(exc)}


@app.put("/api/files")
def save_file(req: FileSaveRequest):
    """Save/update a file in the workspace."""
    workspace = Path(SETTINGS.workspace_path)
    target = (workspace / req.path).resolve()
    if workspace.resolve() not in target.parents and target != workspace.resolve():
        return {"error": "Path escapes workspace"}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(req.content, encoding="utf-8")
        return {"status": "success", "path": str(target.relative_to(workspace)), "size": len(req.content)}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/search")
def search_code(req: SearchRequest):
    """Search across workspace files."""
    workspace = Path(SETTINGS.workspace_path)
    if not workspace.exists():
        return {"results": [], "total": 0}

    results = []
    query_lower = req.query.lower()
    text_suffixes = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".toml", ".yml", ".yaml", ".css", ".html"}
    ignored_dirs = {".git", "node_modules", "__pycache__", ".next", "dist", "venv", ".venv", "build"}

    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for fname in files:
            if len(results) >= req.max_results:
                break
            fpath = Path(root) / fname
            if fpath.suffix not in text_suffixes:
                continue

            rel_path = str(fpath.relative_to(workspace))

            if req.scope == "files":
                if query_lower in fname.lower():
                    results.append({"file": rel_path, "line": 0, "match": fname, "context": ""})
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if query_lower in line.lower():
                        results.append({
                            "file": rel_path,
                            "line": line_num,
                            "match": line.strip()[:200],
                            "context": fname,
                        })
                        if len(results) >= req.max_results:
                            break
            except Exception:
                continue

    return {"results": results, "total": len(results), "query": req.query, "scope": req.scope}


# ─── Agent Status ─────────────────────────────────────────────────

_AGENT_STATUS = {
    "status": "idle",
    "phase": None,
    "runtime_ms": 0,
    "last_task": None,
    "started_at": None,
}


@app.get("/api/agent/status")
def get_agent_status():
    """Return current agent execution status."""
    return _AGENT_STATUS


@app.post("/api/agent/stop")
def stop_agent():
    """Request the running agent to stop."""
    global _GLOBAL_AGENT
    if "_GLOBAL_AGENT" in globals() and _GLOBAL_AGENT is not None:
        _GLOBAL_AGENT = None
        _AGENT_STATUS["status"] = "stopped"
        _AGENT_STATUS["phase"] = None
        return {"status": "stopped", "message": "Agent stopped"}
    return {"status": "idle", "message": "No agent running"}


# ─── API Keys Management ─────────────────────────────────────────

class APIKeyRequest(BaseModel):
    provider: str  # "gemini" | "openai" | "anthropic" | "openrouter"
    api_key: str


@app.get("/api/keys")
def list_api_keys():
    """Return which API key providers are configured (without exposing keys)."""
    providers = {
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
    }
    return {"providers": providers}


@app.post("/api/keys")
def set_api_key(req: APIKeyRequest):
    """Set an API key for a provider (session-only, stored in env)."""
    env_map = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_var = env_map.get(req.provider)
    if not env_var:
        return {"status": "error", "message": f"Unknown provider: {req.provider}"}
    os.environ[env_var] = req.api_key
    return {"status": "success", "provider": req.provider, "message": f"{req.provider} API key configured"}


@app.websocket("/ws/agent")
async def agent_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id = None
    try:
        payload = await websocket.receive_json()
        task = payload.get("task", "") if isinstance(payload, dict) else ""
        workspace_path = payload.get("workspace_path", "") if isinstance(payload, dict) else ""
        model = payload.get("model", "") if isinstance(payload, dict) else ""
        plan_mode = payload.get("plan_mode", "autonomous") if isinstance(payload, dict) else "autonomous"
        github_token = payload.get("github_token", "") if isinstance(payload, dict) else ""
        session_id = payload.get("session_id", "") if isinstance(payload, dict) else ""

        print(f"[WS] Received: task={task!r}, workspace_path={workspace_path!r}, model={model!r}, plan_mode={plan_mode!r}, github_token={'***' if github_token else 'none'}, session_id={session_id!r}")

        # Always use server workspace (ignore client path)
        workspace_path = _DEFAULT_WORKSPACE
        print(f"[WS] Using server workspace: {workspace_path}")

        # Store GitHub token if provided
        if github_token:
            SETTINGS.github_token = github_token

        if not isinstance(task, str) or not task:
            await websocket.send_json({"type": "error", "message": "task is required"})
            await websocket.close()
            return

        # Ensure workspace exists
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            ws_path.mkdir(parents=True, exist_ok=True)

        print(f"[WS] Using workspace: {workspace_path}")

        # Create or update session
        session_manager = get_session_manager()
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())

        session = session_manager.get_session(session_id)
        if session:
            # Update existing session
            session_manager.update_session(session_id, status="running")
        else:
            # Create new session with auto-generated title
            session = session_manager.create_session(
                session_id=session_id,
                task=task,
                workspace_path=workspace_path,
                model=model or "gemini-2.0-flash-exp"
            )

        # Send session info to client
        await websocket.send_json({
            "type": "session_created",
            "session_id": session_id,
            "title": session.title
        })

        _AGENT_STATUS["status"] = "running"
        _AGENT_STATUS["phase"] = "observe"
        _AGENT_STATUS["last_task"] = task
        _AGENT_STATUS["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        _AGENT_STATUS["runtime_ms"] = 0

        try:
            global _GLOBAL_AGENT
            from backend.config import load_config
            config = load_config(workspace_path)
            # Always recreate agent to ensure latest code is loaded
            _GLOBAL_AGENT = SharrowkinAgent(config=config)
            async for event in _GLOBAL_AGENT.run(task, workspace_path, plan_mode=plan_mode):
                if isinstance(event, dict):
                    if event.get("type") == "phase_change":
                        _AGENT_STATUS["phase"] = event.get("phase")
                    elif event.get("type") == "status" and event.get("status") == "done":
                        _AGENT_STATUS["status"] = "idle"
                        _AGENT_STATUS["phase"] = None
                await websocket.send_json(event)
        except Exception as exc:
            print(f"[WS] Agent error: {exc}")
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

        try:
            await websocket.close()
        except Exception:
            pass
    except WebSocketDisconnect:
        # Update session status on disconnect
        if session_id:
            session_manager = get_session_manager()
            session_manager.update_session(session_id, status="completed")
        return
    except Exception as exc:
        print(f"[WS] Unhandled error: {exc}")
        # Update session status on error
        if session_id:
            session_manager = get_session_manager()
            session_manager.update_session(session_id, status="failed")
        try:
            await websocket.send_json({"type": "error", "message": f"Server error: {exc}"})
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# GitHub Integration Endpoints
# ============================================================================

# In-memory storage for OAuth states and tokens (use Redis in production)
_OAUTH_STATES: dict[str, dict] = {}
_GITHUB_TOKENS: dict[str, str] = {}  # user_id -> access_token


class GitHubAuthRequest(BaseModel):
    scopes: list[str] = ["repo", "user", "read:org", "workflow"]


class GitHubCallbackRequest(BaseModel):
    code: str
    state: str


class GitHubRepoRequest(BaseModel):
    repo_url: str
    dest_path: str
    branch: str | None = None


class GitHubPRRequest(BaseModel):
    owner: str
    repo: str
    title: str
    head: str
    base: str = "main"
    body: str = ""
    draft: bool = False


@app.post("/api/github/setup-agent-profile")
async def setup_agent_profile():
    """Setup git profile for Sharrowkin Agent."""
    try:
        # Get GitHub user if connected
        token = None
        for stored_token in _GITHUB_TOKENS.values():
            token = stored_token
            break

        if token:
            github_api = GitHubAPI(token)
            user = await github_api.get_user()

            # Setup git config globally for agent
            subprocess.run(["git", "config", "--global", "user.name", f"Sharrowkin Agent ({user.get('login')})"], check=True)
            subprocess.run(["git", "config", "--global", "user.email", f"{user.get('login')}+sharrowkin@users.noreply.github.com"], check=True)

            return {
                "status": "success",
                "message": f"Git profile configured for Sharrowkin Agent ({user.get('login')})",
                "config": {
                    "user.name": f"Sharrowkin Agent ({user.get('login')})",
                    "user.email": f"{user.get('login')}+sharrowkin@users.noreply.github.com"
                }
            }
        else:
            # Setup default agent profile
            subprocess.run(["git", "config", "--global", "user.name", "Sharrowkin Agent"], check=True)
            subprocess.run(["git", "config", "--global", "user.email", "agent@sharrowkin.ai"], check=True)

            return {
                "status": "success",
                "message": "Git profile configured for Sharrowkin Agent (default)",
                "config": {
                    "user.name": "Sharrowkin Agent",
                    "user.email": "agent@sharrowkin.ai"
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to setup git profile: {str(e)}")


@app.get("/api/github/status")
async def github_status():
    """Check if GitHub is connected and repository is configured."""
    # Try to get token from multiple sources
    token = None

    # 1. Try SETTINGS.github_token (from WebSocket)
    if SETTINGS.github_token:
        token = SETTINGS.github_token

    # 2. Try _GITHUB_TOKENS (from OAuth callback)
    if not token:
        for stored_token in _GITHUB_TOKENS.values():
            token = stored_token
            break

    if not token:
        return {
            "connected": False,
            "repository": None,
            "message": "GitHub not connected. Please connect in Settings."
        }

    try:
        github_api = GitHubAPI(token)
        user = await github_api.get_user()

        # Check if workspace path is set and is a git repo
        workspace_path = Path(os.getenv("WORKSPACE_PATH", ""))
        if not workspace_path.exists():
            return {
                "connected": True,
                "user": user.get("login"),
                "repository": None,
                "message": "Workspace path not configured"
            }

        # Try to get git remote
        try:
            repo = GitHubRepository(workspace_path)
            remote_url = repo.get_remote_url()
            current_branch = repo.get_current_branch()
            is_clean = repo.is_clean()

            return {
                "connected": True,
                "user": user.get("login"),
                "repository": {
                    "url": remote_url,
                    "branch": current_branch,
                    "clean": is_clean
                },
                "message": "GitHub connected and repository configured"
            }
        except Exception:
            return {
                "connected": True,
                "user": user.get("login"),
                "repository": None,
                "message": "Workspace is not a git repository"
            }
    except Exception as e:
        return {
            "connected": False,
            "repository": None,
            "message": f"GitHub connection error: {str(e)}"
        }


@app.get("/api/github/oauth/authorize")
async def github_oauth_authorize(request: Request):
    """Start GitHub OAuth flow."""
    try:
        oauth = GitHubOAuth()
        if not oauth.is_configured:
            return {
                "status": "error",
                "message": "GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env"
            }

        auth_url, state = oauth.get_authorization_url()

        # Store state for verification
        _OAUTH_STATES[state] = {
            "created_at": time.time(),
            "ip": request.client.host if request.client else "unknown"
        }

        return {
            "status": "success",
            "authorization_url": auth_url,
            "state": state
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/api/github/init-repo")
async def init_repo(request: dict):
    """Initialize workspace as git repository and connect to GitHub."""
    workspace_path = Path(request.get("workspace_path", ""))
    repo_url = request.get("repo_url", "")

    if not workspace_path.exists():
        raise HTTPException(status_code=400, detail="Workspace path does not exist")

    token = None
    for stored_token in _GITHUB_TOKENS.values():
        token = stored_token
        break

    if not token:
        raise HTTPException(status_code=401, detail="GitHub not connected")

    try:
        # Check if already a git repo
        try:
            repo = GitHubRepository(workspace_path)
            existing_remote = repo.get_remote_url()
            return {
                "status": "success",
                "message": f"Already a git repository: {existing_remote}",
                "remote_url": existing_remote
            }
        except Exception:
            pass

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=workspace_path, check=True)
        subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=workspace_path, check=True)

        # Set git config
        repo = GitHubRepository(workspace_path)
        github_api = GitHubAPI(token)
        user = await github_api.get_user()

        repo.set_config("user.name", user.get("name") or user.get("login"))
        repo.set_config("user.email", user.get("email") or f"{user.get('login')}@users.noreply.github.com")

        return {
            "status": "success",
            "message": "Repository initialized successfully",
            "remote_url": repo_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize repository: {str(e)}")

@app.get("/api/github/oauth/authorize")
async def github_oauth_authorize(request: Request):
    """Start GitHub OAuth flow."""
    try:
        oauth = GitHubOAuth()
        if not oauth.is_configured:
            return {
                "status": "error",
                "message": "GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env"
            }

        auth_url, state = oauth.get_authorization_url()

        # Store state for verification
        _OAUTH_STATES[state] = {
            "created_at": time.time(),
            "ip": request.client.host if request.client else "unknown"
        }

        return {
            "status": "success",
            "authorization_url": auth_url,
            "state": state
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/api/github/oauth/callback")
async def github_oauth_callback(callback: GitHubCallbackRequest):
    """Handle GitHub OAuth callback."""
    try:
        # Verify state
        if callback.state not in _OAUTH_STATES:
            return {"status": "error", "message": "Invalid state parameter"}

        # Clean up old states (older than 10 minutes)
        current_time = time.time()
        _OAUTH_STATES.clear()  # Simple cleanup for now

        oauth = GitHubOAuth()
        token_data = await oauth.exchange_code_for_token(callback.code)
        access_token = token_data["access_token"]

        # Get user info
        user_info = await oauth.get_user_info(access_token)
        user_id = str(user_info["id"])

        # Store token (use encrypted storage in production)
        _GITHUB_TOKENS[user_id] = access_token

        return {
            "status": "success",
            "access_token": access_token,
            "user": {
                "id": user_info["id"],
                "login": user_info["login"],
                "name": user_info.get("name"),
                "email": user_info.get("email"),
                "avatar_url": user_info.get("avatar_url"),
            },
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/api/github/user")
async def github_get_user(authorization: str = ""):
    """Get authenticated GitHub user."""
    try:
        from backend.integrations.github import GitHubAPI

        # Try to get token from header or from SETTINGS
        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            token = SETTINGS.github_token
        if not token:
            # Try to get from stored tokens
            for stored_token in _GITHUB_TOKENS.values():
                token = stored_token
                break
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        user = await api.get_user()

        return {
            "status": "success",
            "user": user
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/api/github/repos")
async def github_list_repos(authorization: str = ""):
    """List user's GitHub repositories."""
    try:
        from backend.integrations.github import GitHubAPI

        # Try to get token from header or from SETTINGS
        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            token = SETTINGS.github_token
        if not token:
            # Try to get from stored tokens
            for stored_token in _GITHUB_TOKENS.values():
                token = stored_token
                break
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        repos = await api.list_repos()

        return {
            "status": "success",
            "repos": repos
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/api/github/repos/clone")
async def github_clone_repo(repo_request: GitHubRepoRequest):
    """Clone a GitHub repository."""
    try:
        from backend.integrations.github import GitHubRepository

        repo = GitHubRepository.clone(
            repo_url=repo_request.repo_url,
            dest_path=repo_request.dest_path,
            branch=repo_request.branch,
            depth=1  # Shallow clone by default
        )

        return {
            "status": "success",
            "message": f"Repository cloned to {repo_request.dest_path}",
            "path": str(repo.repo_path)
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/api/github/repos/{owner}/{repo}/branches")
async def github_list_branches(owner: str, repo: str, authorization: str = ""):
    """List branches in repository."""
    try:
        from backend.integrations.github import GitHubAPI

        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        branches = await api.list_branches(owner, repo)

        return {
            "status": "success",
            "branches": branches
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/api/github/repos/{owner}/{repo}/pr")
async def github_create_pr(owner: str, repo: str, pr_request: GitHubPRRequest, authorization: str = ""):
    """Create a pull request."""
    try:
        from backend.integrations.github import GitHubAPI

        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        pr = await api.create_pr(
            owner=owner,
            repo=repo,
            title=pr_request.title,
            head=pr_request.head,
            base=pr_request.base,
            body=pr_request.body,
            draft=pr_request.draft
        )

        return {
            "status": "success",
            "pr": pr
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/api/github/repos/{owner}/{repo}/prs")
async def github_list_prs(owner: str, repo: str, state: str = "open", authorization: str = ""):
    """List pull requests."""
    try:
        from backend.integrations.github import GitHubAPI

        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        prs = await api.list_prs(owner, repo, state)

        return {
            "status": "success",
            "prs": prs
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/api/github/repos/{owner}/{repo}/contents")
async def github_get_contents(owner: str, repo: str, path: str = "", ref: str = "main", authorization: str = ""):
    """Get contents of a file or directory in repository."""
    try:
        from backend.integrations.github import GitHubAPI

        # Try to get token from multiple sources
        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            token = SETTINGS.github_token
        if not token:
            for stored_token in _GITHUB_TOKENS.values():
                token = stored_token
                break
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        contents = await api.get_contents(owner, repo, path, ref)

        return {
            "status": "success",
            "contents": contents
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/api/github/repos/{owner}/{repo}/file")
async def github_get_file(owner: str, repo: str, path: str, ref: str = "main", authorization: str = ""):
    """Get decoded content of a file."""
    try:
        from backend.integrations.github import GitHubAPI

        # Try to get token from multiple sources
        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            token = SETTINGS.github_token
        if not token:
            for stored_token in _GITHUB_TOKENS.values():
                token = stored_token
                break
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        content = await api.get_file_content(owner, repo, path, ref)

        return {
            "status": "success",
            "content": content,
            "path": path
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/api/github/repos/{owner}/{repo}/tree")
async def github_get_tree(owner: str, repo: str, sha: str = "main", recursive: bool = True, authorization: str = ""):
    """Get repository tree (file structure)."""
    try:
        from backend.integrations.github import GitHubAPI

        # Try to get token from multiple sources
        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            token = SETTINGS.github_token
        if not token:
            for stored_token in _GITHUB_TOKENS.values():
                token = stored_token
                break
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        tree = await api.get_tree(owner, repo, sha, recursive)

        return {
            "status": "success",
            "tree": tree
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.put("/api/github/repos/{owner}/{repo}/file")
async def github_update_file(owner: str, repo: str, file_data: dict, authorization: str = ""):
    """Create or update a file in repository."""
    try:
        from backend.integrations.github import GitHubAPI

        # Try to get token from multiple sources
        token = authorization.replace("Bearer ", "") if authorization else ""
        if not token:
            token = SETTINGS.github_token
        if not token:
            for stored_token in _GITHUB_TOKENS.values():
                token = stored_token
                break
        if not token:
            return {"status": "error", "message": "No authorization token provided"}

        api = GitHubAPI(token)
        result = await api.create_or_update_file(
            owner=owner,
            repo=repo,
            path=file_data.get("path"),
            content=file_data.get("content"),
            message=file_data.get("message", "Update file"),
            branch=file_data.get("branch", "main"),
            sha=file_data.get("sha"),
        )

        return {
            "status": "success",
            "commit": result
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

