"""Real Sharrowkin cognitive agent loop with live thinking stream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
import math
import time
from typing import Any
import os
import httpx
import subprocess
import tracemalloc  # ✅ NEW: Memory profiling

from monitoring.telemetry import get_tracer
from monitoring.memory_profiler import get_memory_profiler, log_memory  # ✅ NEW: Memory profiling
from memory.persistence import PersistentMemoryManager  # ✅ NEW: Checkpoint saving
from agent.event_stream import (
    AgentOutcome,
    AgentStatus,
    EventBus,
    PhaseId,
    PhaseStatus,
)
from agent.resilience import PhaseGuard, RetryPolicy, degrade_on_error, retry_async
from agent.checkpoints import (
    Checkpoint,
    CheckpointPhase,
    CheckpointStore,
    SCHEMA_VERSION as CHECKPOINT_SCHEMA_VERSION,
    ToolCallSnapshot,
)
from core.llm.client import AUTONOMOUS_AGENT_POLICY, GeminiClient, GeminiConfigurationError, GeneratedPatch
from agent.tool_loop import ToolLoop
from agent.agent_tools import AgentToolbox
from core import types
from memory import MemoryBridge

from personas import get_persona_manager, inject_persona, format_log
from personas.llm_integration import LogType
from core.tools import (
    ProposedFileChange,
    apply_changes,
    git_diff,
    resolve_workspace,
    run_pytest,
    scan_workspace,
    summarize_workspace,
    search_web,
    fetch_url,
    run_terminal_command,
    read_file,
    list_files,
    github_list_repos,
    github_get_repo_info,
    github_list_branches,
    github_create_pr,
    github_clone_repo,
)
from analysis.code.dependency import DependencyAnalyzer
from analysis.code.semantic_graph import SemanticGraph, SemanticGraphBuilder
from config.settings import AgentConfig, load_config
from agent.workspace_cache import WorkspaceCache, CachedWorkspace
from agent.failure_analyzer import FailureAnalyzer, FailureContext
from core.plugins.base import PluginManager
from core.cached_workspace_manager import CachedWorkspaceManager

# ✅ NEW: Learning modules integration
from learning.strategy_optimizer import StrategyOptimizer
from learning.style_learner import StyleLearner
from learning.meta_learner import MetaLearner

PHASES = ["Observe", "Recall", "Reason", "Stabilize", "Commit"]

# Retry policy for LLM calls (Requirement 6.3): 3 attempts, 1s base delay,
# 30s max delay, ±25% jitter. The default_classify from agent.resilience
# already handles httpx timeouts, 429, 503 as transient.
LLM_RETRY_POLICY = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0, jitter=0.25)


@dataclass(slots=True)
class FailureRecord:
    iteration: int
    changed_files: list[str]
    error: str
    patch_diff: str


@dataclass(slots=True)
class AgentRunState:
    task: str
    workspace: Path
    states: list[str]
    actions: list[str]
    tools_used: list[str]
    workspace_summary: str = ""
    memory_context: str = ""
    memory_context_structured: dict = field(default_factory=dict)  # NEW: structured memory
    last_error: str = ""
    final_diff: str = ""
    changes_made: bool = False
    last_rationale: str = ""
    complexity_avg: float = 0.0
    circular_dependencies: int = 0
    most_complex_functions: list[dict] = field(default_factory=list)
    current_changed_files: list[str] = field(default_factory=list)
    semantic_graph: Any = None  # SemanticGraph instance for Phase 3
    selected_repo: str = ""  # GitHub repository (owner/repo)
    task_graph: Any = None  # TaskGraph for hierarchical planning
    total_files: int = 0  # Total files in workspace


def localize_ast_error(workspace: Path, file_name: str, line_number: int) -> dict[str, str] | None:
    """Parse the Python AST to localize and extract error contexts with functions/classes."""
    import ast
    try:
        file_path = workspace / file_name
        if not file_path.exists():
            # Search workspace for matching file name
            for p in workspace.rglob(file_name):
                if p.is_file():
                    file_path = p
                    break
        if not file_path.exists():
            return None
            
        code = file_path.read_text(encoding="utf-8", errors="replace")
        lines = code.splitlines()
        
        # Parse the AST to find the node enclosing the error line
        try:
            tree = ast.parse(code)
            
            enclosing_func = "Global context"
            enclosing_class = "None"
            func_source = ""
            
            class ErrorLocFinder(ast.NodeVisitor):
                def __init__(self, target_line):
                    self.target_line = target_line
                    self.current_class = None
                    self.found_func = None
                    self.found_class = None
                    self.func_node = None
                    
                def visit_ClassDef(self, node):
                    old_class = self.current_class
                    self.current_class = node.name
                    self.generic_visit(node)
                    self.current_class = old_class
                    
                def visit_FunctionDef(self, node):
                    # Check if target line is inside this function
                    end_line = getattr(node, "end_lineno", len(lines))
                    if node.lineno <= self.target_line <= end_line:
                        self.found_func = node.name
                        self.found_class = self.current_class
                        self.func_node = node
                    self.generic_visit(node)
                    
                def visit_AsyncFunctionDef(self, node):
                    self.visit_FunctionDef(node)
                    
            finder = ErrorLocFinder(line_number)
            finder.visit(tree)
            
            if finder.found_func:
                enclosing_func = finder.found_func
                enclosing_class = finder.found_class or "None"
                start = finder.func_node.lineno - 1
                end = getattr(finder.func_node, "end_lineno", line_number + 10)
                func_source = "\n".join(lines[start:end])
                
            # Get snippet around target line
            start_idx = max(0, line_number - 6)
            end_idx = min(len(lines), line_number + 5)
            snippet = "\n".join(f"{i+1}: {lines[i]}" for i in range(start_idx, end_idx))
            
            return {
                "file": str(file_path.relative_to(workspace) if workspace in file_path.parents else file_path.name),
                "enclosing_class": enclosing_class,
                "enclosing_func": enclosing_func,
                "snippet": snippet,
                "func_source": func_source
            }
        except Exception as ast_e:
            print(f"[AST Error Localizer] AST Parsing failed: {ast_e}. Falling back to text-based extraction...")
            # Text-based backtracking to find class and def declarations
            enclosing_func = "Global context (text fallback)"
            enclosing_class = "None"
            
            # Start backtracking from the error line to line 0
            err_idx = min(len(lines) - 1, max(0, line_number - 1))
            
            import re
            func_indent = 999
            class_indent = 999
            
            # Find enclosing function
            for i in range(err_idx, -1, -1):
                line = lines[i]
                stripped = line.strip()
                if not stripped:
                    continue
                match = re.match(r"^(\s*)(async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
                if match:
                    indent = len(match.group(1))
                    if indent < func_indent:
                        enclosing_func = match.group(3)
                        func_indent = indent
                        break
                        
            # Find enclosing class (must be at an even smaller indent than the function if any)
            for i in range(err_idx, -1, -1):
                line = lines[i]
                stripped = line.strip()
                if not stripped:
                    continue
                match = re.match(r"^(\s*)class\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
                if match:
                    indent = len(match.group(1))
                    if indent < func_indent and indent < class_indent:
                        enclosing_class = match.group(2)
                        class_indent = indent
                        break
            
            # Snippet around target line
            start_idx = max(0, line_number - 6)
            end_idx = min(len(lines), line_number + 5)
            snippet = "\n".join(f"{i+1}: {lines[i]}" for i in range(start_idx, end_idx))
            
            return {
                "file": str(file_path.relative_to(workspace) if workspace in file_path.parents else file_path.name),
                "enclosing_class": enclosing_class,
                "enclosing_func": enclosing_func,
                "snippet": snippet,
                "func_source": "# [Syntax Error fallback - raw surrounding lines]\n" + "\n".join(lines[max(0, line_number - 10):min(len(lines), line_number + 15)])
            }
    except Exception as e:
        print(f"[AST Error Localizer] Error: {e}")
        return None


class SharrowkinAgent:
    def __init__(self, gemini_client: GeminiClient | None = None, max_iterations: int | None = None, config: AgentConfig | None = None) -> None:
        self.config = config or load_config()
        self.gemini = gemini_client or GeminiClient(model=self.config.llm.model)
        self.max_iterations = max_iterations if max_iterations is not None else self.config.execution.max_iterations
        self.conversation_history: list[dict] = []
        self.persona_manager = get_persona_manager()
        self.selected_repo: str = ""  # Persistent selected repository across requests
        self.workspace_cache = WorkspaceCache(ttl_seconds=3600, max_entries=10)  # Cache workspace scans
        self.workspace_manager: CachedWorkspaceManager | None = None  # ✅ NEW: File watcher integration
        self.failure_history: list[FailureRecord] = []
        self.failure_analyzer = FailureAnalyzer()  # NEW: Analyze failures for learning
        self._tracer = get_tracer()
        self.plugins = PluginManager(self)
        self.memory_profiler = get_memory_profiler()  # ✅ NEW: Memory profiling
        self.checkpoint_manager: PersistentMemoryManager | None = None  # ✅ NEW: Checkpoint manager
        self.conversation: Any = None  # ✅ NEW: ConversationHistory instance

        # ✅ NEW: Learning modules (initialized per workspace in run())
        self.strategy_optimizer: StrategyOptimizer | None = None
        self.style_learner: StyleLearner | None = None
        self.meta_learner: MetaLearner | None = None

        # Task 5.1: optional EventBus for the new Event_Stream contract.
        # Set per-run via SharrowkinAgent.run(event_bus=...). When ``None`` the
        # legacy dict-emitter helpers (see ``_phase``/``_status``/...) are the
        # only output channel; when present, top-level status transitions are
        # mirrored to the bus in addition to the legacy dicts. The legacy
        # helpers are scheduled for removal in task 21.1 (cleanup).
        self._event_bus: EventBus | None = None
        self._run_started_monotonic: float | None = None

        # Log initial memory state
        self.memory_profiler.log_snapshot("Agent initialized")

    def start_workspace_watching(self, workspace: Path):
        """✅ NEW: Start file watcher for incremental cache updates."""
        if self.workspace_manager is None:
            self.workspace_manager = CachedWorkspaceManager(workspace, ttl_seconds=3600)
            self.workspace_manager.start_watching()
            print(f"[AGENT] Started workspace file watcher for {workspace}")

    def stop_workspace_watching(self):
        """✅ NEW: Stop file watcher."""
        if self.workspace_manager is not None:
            self.workspace_manager.stop_watching()
            self.workspace_manager = None
            print(f"[AGENT] Stopped workspace file watcher")

    def _get_energy_ledger(self, state: AgentRunState, memory: MemoryBridge, phase: str, iteration: int = 1) -> dict:
        """Compute the algorithmic energy footprint of cognitive execution."""
        try:
            # 1. Chars read: sum of workspace_summary length + memory_context length + last_error length
            chars_read = len(state.workspace_summary) + len(state.memory_context) + len(state.last_error)
            if chars_read == 0:
                chars_read = 1000  # Default fallback
                
            # 2. Chars written: length of final diff or changes applied
            chars_written = len(state.final_diff)
            if not chars_written and state.changes_made:
                chars_written = 500  # Fallback for changes made
            
            # 3. Context characters
            chars_context = len(state.task)
            
            # 4. Multi-agent/experts dimension
            k = 0
            if memory.rld and memory.rld.genes:
                k = len(memory.rld.genes)
            expert_cost = 18.0
            
            # Model complexity: O(Chars_read * log Chars_read + Chars_written^2 + Chars_context * k)
            log_part = math.log2(chars_read) if chars_read > 1 else 1.0
            read_complexity = chars_read * log_part
            
            write_complexity = chars_written ** 2
            
            context_complexity = chars_context * k * expert_cost
            
            # Calculate total computational complexity score
            complexity_score = read_complexity + write_complexity + context_complexity
            
            # Translate score into realistic FLOP-equivalent numbers (GigaFLOPS)
            flops = complexity_score / 1e3
            if flops < 1.0:
                flops = 1.0
            elif flops > 10000.0:
                flops = 10000.0 + math.log(flops) * 100.0
                
            # Map complexity components to energy units
            forward = round(read_complexity / 2000.0 + 5.0, 2)
            mem_search = round(context_complexity / 50.0 + (12.5 if memory.enabled else 4.0), 2)
            
            # Trace Replay activations
            replayed_count = 0
            if hasattr(memory, "trace_memory") and memory.trace_memory.traces:
                replayed_count = min(2, len(memory.trace_memory.traces))
            trace_replay = round(replayed_count * 22.0 + (chars_read * 0.001), 2)
            
            # Active Multi-turn Expert Reasoning
            expert_reasoning = round(iteration * 35.5 + (write_complexity / 50000.0), 2)
            
            # Attractor update costs (Hebbian outer product complexity: 2 * dim^2)
            hebbian = 0.0
            if phase.lower() == "commit":
                dim = getattr(memory.memory_field, "dim", 128)
                hebbian = round((2 * (dim ** 2)) / 100.0, 2)
                
            total = round(forward + mem_search + trace_replay + expert_reasoning + hebbian, 2)
            
            return {
                "forward": forward,
                "memory_search": mem_search,
                "trace_replay": trace_replay,
                "expert_reasoning": expert_reasoning,
                "hebbian": hebbian,
                "total": total,
                "flops_g": round(flops / 10.0, 2),  # FLOPS in GigaFLOPS
                "chars_read": chars_read,
                "chars_written": chars_written
            }
        except Exception:
            return {
                "forward": 15.0,
                "memory_search": 5.0,
                "trace_replay": 10.0,
                "expert_reasoning": 25.0,
                "hebbian": 0.0,
                "total": 55.0,
                "flops_g": 5.5,
                "chars_read": 1000,
                "chars_written": 0
            }

    # --- helper emitters ---------------------------------------------------
    # DEPRECATED (task 5.1): the dict-shaped emitters below are the legacy
    # event channel kept for backward compatibility with the current
    # WebSocket router and UI. They run in parallel with the new
    # :class:`agent.event_stream.EventBus` (see ``self._event_bus``). The
    # legacy helpers will be removed in task 21.1 once the WebSocket router
    # speaks only the v=1 envelope (``EventBus``-emitted) format.
    def _phase(self, name: str, status: str) -> dict[str, object]:
        return {"type": "phase_change", "phase": name.lower(), "status": status}

    def _log(self, level: str, message: str) -> dict[str, object]:
        return {"type": "log", "level": level, "message": message}

    def _task_update(self, task_id: str, status: str) -> dict[str, object]:
        """Emit task status update for frontend (legacy, deprecated — see task 21.1)."""
        return {"type": "task_update", "task_id": task_id, "status": status}

    def _status(self, status: str, message: str = "") -> dict[str, object]:
        result = {"type": "status", "status": status}
        if message:
            result["message"] = message
        return result

    def _repo_selector(self, repos: list[dict], prompt: str = "Выберите репозиторий:") -> dict[str, object]:
        """Send repository selector card to frontend (legacy, deprecated — see task 21.1)."""
        return {
            "type": "repo_selector",
            "prompt": prompt,
            "repos": repos
        }

    def _thinking(self, text: str) -> dict[str, object]:
        """Emit a 'thinking' event so the frontend shows live agent reasoning (legacy, deprecated — see task 21.1)."""
        return {"type": "thinking", "content": text}

    def _tool_activity(
        self,
        name: str,
        *,
        status: str = "done",
        message: str = "",
        target: str = "",
        duration_ms: int | None = None,
    ) -> dict[str, object]:
        event: dict[str, object] = {
            "type": "tool_activity",
            "name": name,
            "status": status,
            "message": message,
            "target": target,
        }
        if duration_ms is not None:
            event["duration_ms"] = duration_ms
        return event

    def _tool_call(
        self,
        tool: str,
        *,
        status: str = "done",
        target: str = "",
        detail: str = "",
        lines_changed: int = 0,
        duration_ms: int = 0,
        args: dict | None = None,
        result: str = "",
    ) -> dict[str, object]:
        """Emit a tool_call event for Devin-style tool invocation display (legacy, deprecated — see task 21.1)."""
        return {
            "type": "tool_call",
            "tool": tool,
            "status": status,
            "target": target,
            "detail": detail,
            "lines_changed": lines_changed,
            "duration_ms": duration_ms,
            # Structured input/output so the UI can render the live file
            # content in the Agent Computer pane.
            "args": args or {},
            "result": result[:8000] if result else "",
        }

    # --- EventBus mirroring (task 5.1) -------------------------------------
    # Minimal helpers that forward a few top-level run() lifecycle events to
    # the injected :class:`EventBus`. Phase-level mirroring (observe/recall/
    # reason/stabilize/commit) and tool-call mirroring are left to task 5.2
    # (``PhaseGuard``) and task 5.3+. The bus is optional: when not injected,
    # these helpers are no-ops, so existing call sites stay unchanged.

    def _bus_runtime_ms(self) -> int:
        """Elapsed milliseconds since the start of the current run, or 0."""
        if self._run_started_monotonic is None:
            return 0
        return max(0, int((time.monotonic() - self._run_started_monotonic) * 1000))

    async def _bus_status(
        self,
        status: AgentStatus | str,
        *,
        message: str | None = None,
        include_runtime: bool = False,
    ) -> None:
        """Mirror a status transition to the EventBus, if one is attached.

        Failures here are swallowed: the legacy dict-emitter (the ``yield
        self._status(...)`` next to every call site) remains the source of
        truth until task 21.1, so a transport hiccup on the bus must never
        break the existing flow.
        """
        bus = self._event_bus
        if bus is None:
            return
        try:
            await bus.status(
                status,
                message=message,
                runtime_ms=self._bus_runtime_ms() if include_runtime else None,
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[AGENT][EventBus] status mirror failed: {exc}")

    async def _bus_agent_complete(self, outcome: AgentOutcome | str) -> None:
        """Mirror a terminal ``agent_complete`` event to the EventBus, if attached."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            await bus.agent_complete(outcome, runtime_ms=self._bus_runtime_ms())
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[AGENT][EventBus] agent_complete mirror failed: {exc}")

    # --- Task 5.4: safe memory access helpers ------------------------------

    async def _safe_attractors(self, memory: "MemoryBridge", limit: int = 8) -> list:
        """Get top associations from memory_field, degrading to [] on error."""
        if not memory.memory_field:
            return []
        return await degrade_on_error(
            lambda: asyncio.to_thread(memory.memory_field.get_top_associations, limit=limit),
            fallback=[],
            code="memory_field_get_associations_failed",
            bus=self._event_bus,
        )

    async def _safe_recall_structured(
        self, memory: "MemoryBridge", task: str, conversation_context: str
    ) -> dict:
        """Recall structured memory, degrading to empty dict on error."""
        return await degrade_on_error(
            lambda: asyncio.to_thread(memory.recall_structured, task, conversation_context),
            fallback={"full_context": "", "has_memory": False, "similar_solutions": [], "rld_genes": [], "dsm_segments": []},
            code="memory_recall_structured_failed",
            bus=self._event_bus,
        )

    async def _safe_learn_project(self, memory: "MemoryBridge", workspace_summary: str) -> None:
        """Learn project context, degrading silently on error."""
        await degrade_on_error(
            lambda: asyncio.to_thread(memory.learn_project, workspace_summary),
            fallback=None,
            code="memory_learn_project_failed",
            bus=self._event_bus,
        )

    async def _safe_learn_success(self, memory: "MemoryBridge", **kwargs) -> None:
        """Commit success to memory, degrading silently on error."""
        await degrade_on_error(
            lambda: asyncio.to_thread(memory.learn_success, **kwargs),
            fallback=None,
            code="memory_learn_success_failed",
            bus=self._event_bus,
        )

    async def _generate_plan(self, state: "AgentRunState") -> str:
        """Generate a hierarchical plan and emit it to the UI. Non-fatal.

        Returns a compact markdown checklist for injection into the loop's
        initial context, or "" if planning is unavailable/failed.
        """
        if not self.gemini.configured:
            return ""
        try:
            from planning import HierarchicalPlanner, PlanningContext

            planner = HierarchicalPlanner()
            context = PlanningContext(
                goal=state.task,
                workspace_path=state.workspace,
                available_tools=[
                    "read_file", "list_files", "search_files", "find_symbol",
                    "write_file", "str_replace", "run_command", "run_tests",
                    "verify", "git", "spawn_subagent",
                ],
            )
            task_graph = await asyncio.to_thread(planner.plan, state.task, context)
            state.task_graph = task_graph
            return self._format_plan(task_graph)
        except Exception as exc:
            print(f"[AGENT] Planning failed (non-fatal): {exc}")
            return ""

    def _format_plan(self, task_graph: Any) -> str:
        """Serialize a TaskGraph to a compact markdown checklist.

        Uses real Task fields (title, estimated_time, depends_on). Skips the
        synthetic root task and orders by dependency count so prerequisites
        come first.
        """
        try:
            tasks = [t for t in task_graph.tasks.values() if not t.metadata.get("is_root")]
            if not tasks:
                return ""
            tasks.sort(key=lambda t: (len(t.depends_on), t.title))
            lines: list[str] = []
            for i, t in enumerate(tasks[:20], start=1):
                est = f" (~{t.estimated_time:.0f}min)" if t.estimated_time else ""
                lines.append(f"{i}. {t.title}{est}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _build_hook_runner(self, workspace: Path) -> Any:
        """Build a HookRunner with a safe default policy for the tool loop.

        Denies dangerous shell commands, keeps file ops within the workspace,
        and allows the audited git tool. Returns None if the hooks subsystem
        is unavailable (loop then runs unguarded, as before).
        """
        try:
            from core.hooks.runner import HookRunner
            from core.hooks.policy import (
                PolicyEnforcer, allow, deny, workspace_only,
            )
            from core.hooks.policy import Decision  # noqa: F401  (ensure module import)
            from core.hooks.builtin import create_logging_hooks

            dangerous = {"rm", "sudo", "su", "chmod", "chown", "mkfs", "dd", "curl", "wget", "ssh", "scp"}

            def has_dangerous_token(args: dict) -> bool:
                cmd = (args.get("command") or "").lower()
                return any(tok in cmd.split() for tok in dangerous)

            policies = [
                deny("run_command", when=has_dangerous_token, name="deny_dangerous_commands"),
                allow("write_file", when=workspace_only(str(workspace)), name="write_in_workspace"),
                allow("str_replace", when=workspace_only(str(workspace)), name="edit_in_workspace"),
                allow("*", name="allow_others"),
            ]

            runner = HookRunner()
            runner.register_hook(PolicyEnforcer(policies))
            for hook in create_logging_hooks():
                runner.register_hook(hook)
            return runner
        except Exception as exc:
            print(f"[AGENT] Hook runner unavailable (non-fatal): {exc}")
            return None

    def _build_loop_context(self, state: "AgentRunState", plan_text: str = "") -> str:
        """Assemble the workspace + memory context handed to the tool loop.

        The loop discovers files itself via tools, so this is a lightweight
        orientation block (not full file dumps): workspace summary, complexity
        signals, recalled DSM/RLD/Trace memory, and (if available) a suggested
        plan to follow.
        """
        parts: list[str] = []
        if plan_text:
            parts.append(f"## Suggested plan\n{plan_text}\n(Refine it with the update_plan tool as you work.)")
        if state.workspace_summary:
            parts.append(f"## Workspace\n{state.workspace_summary[:6000]}")
        if state.total_files:
            parts.append(
                f"Files: {state.total_files} | avg complexity: {state.complexity_avg:.1f}"
                f" | circular deps: {state.circular_dependencies}"
            )
        if state.most_complex_functions:
            top = ", ".join(
                f"{f.get('name', '?')}({f.get('complexity', '?')})"
                for f in state.most_complex_functions[:5]
            )
            parts.append(f"Most complex functions: {top}")
        if state.memory_context:
            parts.append(f"## Recalled memory (DSM/RLD/Trace)\n{state.memory_context[:8000]}")
        if state.selected_repo:
            parts.append(f"GitHub repo: {state.selected_repo}")
        return "\n\n".join(parts) if parts else "(empty workspace — create files as needed)"

    async def _safe_learn_failure(self, memory: "MemoryBridge", **kwargs) -> None:
        """Record failure in memory, degrading silently on error."""
        await degrade_on_error(
            lambda: asyncio.to_thread(memory.learn_failure, **kwargs),
            fallback=None,
            code="memory_learn_failure_failed",
            bus=self._event_bus,
        )

    async def _safe_memory_field_update(
        self, memory: "MemoryBridge", from_phase: str, to_phase: str, success: bool
    ) -> None:
        """Update memory field symbolic link, degrading silently on error."""
        if not memory.memory_field:
            return
        await degrade_on_error(
            lambda: asyncio.to_thread(memory.memory_field.update_symbolic, from_phase, to_phase, success=success),
            fallback=None,
            code="memory_field_update_symbolic_failed",
            bus=self._event_bus,
        )

    # --- Task 5.6: Checkpoint v2 save helper --------------------------------

    async def _save_checkpoint_v2(
        self,
        state: "AgentRunState",
        memory: "MemoryBridge",
        current_phase: PhaseId,
        phase_statuses: dict[PhaseId, PhaseStatus],
        session_id: str,
    ) -> None:
        """Save a Checkpoint v2 record after a phase completes or on timer.

        Captures: session_id, current_phase, phase statuses, conversation_ref,
        last_event_seq from bus, cognitive_state.
        """
        from datetime import datetime, timedelta, timezone

        bus = self._event_bus
        try:
            now = datetime.now(timezone.utc)
            created_at = now.isoformat()
            expires_at = (now + timedelta(hours=24)).isoformat()

            # Build phase entries
            phases_list: list[CheckpointPhase] = []
            for pid in PhaseId:
                status = phase_statuses.get(pid, PhaseStatus.PENDING)
                phases_list.append(CheckpointPhase(
                    id=pid,
                    status=status,
                    started_at=created_at if status in (PhaseStatus.RUNNING, PhaseStatus.DONE) else None,
                    completed_at=created_at if status == PhaseStatus.DONE else None,
                    error=None,
                ))

            # Cognitive state snapshot
            cognitive_state: dict = {}
            try:
                cognitive_state = self._get_energy_ledger(state, memory, current_phase.value)
            except Exception:
                pass

            checkpoint = Checkpoint(
                schema_version=CHECKPOINT_SCHEMA_VERSION,
                session_id=session_id,
                workspace=str(state.workspace),
                task=state.task,
                plan_mode="autonomous",
                current_phase=current_phase,
                phases=tuple(phases_list),
                conversation_ref=f".sharrowkin/conversations/{session_id}.json",
                in_flight_tool_calls=(),
                last_event_seq=bus.next_seq if bus else 0,
                cognitive_state=cognitive_state,
                created_at=created_at,
                expires_at=expires_at,
            )

            store = CheckpointStore(state.workspace / ".sharrowkin" / "checkpoints")
            store.save(checkpoint)
            store.prune(workspace=state.workspace, keep=50)
        except Exception as exc:
            print(f"[AGENT][Checkpoint v2] Save failed (non-fatal): {exc}")


    async def _run_phase_guarded(
        self,
        phase_id: PhaseId,
        phase_gen: AsyncIterator[dict[str, object]],
    ) -> tuple[list[dict[str, object]], str]:
        """Execute a phase's async generator inside a PhaseGuard.

        Task 5.2: wraps the phase body so that any internal exception is
        caught by PhaseGuard (which emits ``bus.log(error)`` +
        ``phase_change(error)`` automatically). The process never crashes
        from a phase failure.

        Returns:
            A tuple of (collected_events, outcome) where outcome is one of
            "ok", "error", "timeout".

        The collected_events list contains all dicts yielded by the phase
        generator. The caller is responsible for re-yielding them to the
        outer ``run()`` iterator.

        When no EventBus is attached, the phase runs without a guard (legacy
        path) and outcome is always "ok" unless an exception propagates.
        """
        bus = self._event_bus
        events: list[dict[str, object]] = []

        if bus is None:
            # Legacy path: no EventBus, no PhaseGuard. Just drain the
            # generator and let exceptions propagate as before.
            async for event in phase_gen:
                events.append(event)
            return events, "ok"

        async with PhaseGuard(phase=phase_id, bus=bus) as guard:
            try:
                async for event in phase_gen:
                    events.append(event)
            except Exception:
                # Re-raise so PhaseGuard.__aexit__ can catch it, log it,
                # and set guard.outcome accordingly.
                raise

        return events, guard.outcome

    def _format_history(self) -> str:
        """Format recent conversation history for LLM context."""
        print(f"[DEBUG] _format_history called. Total messages: {len(self.conversation_history)}")
        if len(self.conversation_history) <= 1:
            print(f"[DEBUG] Not enough messages for history (need >1, have {len(self.conversation_history)})")
            return ""
        # Take last 10 messages (excluding the current one which is last)
        recent = self.conversation_history[-11:-1]
        if not recent:
            print(f"[DEBUG] No recent messages after slicing")
            return ""
        lines = []
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Sharrowkin"
            # ✅ OPTIMIZE: Truncate long messages more aggressively
            content = msg["content"]
            if len(content) > 300:  # Reduced from 500
                content = content[:300] + "..."
            lines.append(f"{role}: {content}")
        result = "CONVERSATION HISTORY:\n" + "\n\n".join(lines)
        print(f"[DEBUG] Formatted history with {len(recent)} messages, {len(result)} chars")
        return result

    # --- main run loop ------------------------------------------------------
    async def run(
        self,
        task: str,
        workspace_path: str,
        plan_mode: str = "autonomous",
        *,
        session_id: str | None = None,
        event_bus: EventBus | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Execute a Run.

        The optional ``event_bus`` (task 5.1) wires the new
        :mod:`agent.event_stream` contract into the agent loop. When provided,
        top-level lifecycle transitions (``status``, ``agent_complete``) are
        mirrored to the bus *in addition to* the legacy dict-shaped events
        yielded by the existing ``yield self._status(...)``/``yield
        self._phase(...)`` call sites. The legacy emitters remain the
        canonical channel until task 21.1, when they will be removed.

        Phase-level mirroring (``phase_change``) is intentionally not wired
        here — that lands in task 5.2 (``PhaseGuard``) so we don't duplicate
        the bracketing logic in two places.
        """
        # Stash the bus on ``self`` so phase methods (and future PhaseGuard,
        # task 5.2) can access it without threading another argument through
        # every call site. ``self._run_started_monotonic`` lets the bus
        # mirrors compute runtime_ms without depending on ``state``.
        self._event_bus = event_bus
        self._run_started_monotonic = time.monotonic()
        with self._tracer.start_as_current_span("agent_run") as span:
            span.set_attribute("task", task)
            span.set_attribute("workspace", workspace_path)

            print(f"[AGENT] run() called: task={task!r}, workspace_path={workspace_path!r}, plan_mode={plan_mode!r}")
            workspace = resolve_workspace(workspace_path)

            # ✅ NEW: Start file watcher for incremental updates
            self.start_workspace_watching(workspace)

            state = AgentRunState(
                task=task,
                workspace=workspace,
                states=[],
                actions=[],
                tools_used=[],
            )

            # Extract selected repository from user message if present
            import re
            repo_match = re.search(r'(?:выбрал|selected)\s+(?:репозиторий|repository):\s*([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)', task, re.IGNORECASE)
            if repo_match:
                self.selected_repo = repo_match.group(1)
                state.selected_repo = self.selected_repo
                print(f"[AGENT] Extracted and saved selected repository: {self.selected_repo}")
            elif self.selected_repo:
                # Use previously selected repository
                state.selected_repo = self.selected_repo
                print(f"[AGENT] Using previously selected repository: {self.selected_repo}")
            else:
                print(f"[AGENT] No repository selected yet")

            self.active_memory = MemoryBridge(workspace, config=self.config)
            self.failure_history = []
            memory = self.active_memory

            # ✅ NEW: Initialize conversation history for this session.
            # Use the caller-supplied session_id (stable across messages in the
            # same chat) so the on-disk conversation file is reused and the agent
            # actually remembers prior turns — even after a backend restart.
            # Falling back to a timestamp id only when none is provided keeps the
            # old behavior for ad-hoc/headless runs.
            from memory.conversation import ConversationHistory
            conv_session_id = session_id or f"session_{int(time.time())}"
            self.conversation = ConversationHistory(
                session_id=conv_session_id,
                workspace=workspace,
                max_messages=50,
                context_window=10
            )

            # Hydrate the in-RAM conversation_history (the list _format_history
            # reads) from the disk-backed ConversationHistory so the agent
            # remembers prior turns across backend restarts and session
            # eviction. Only when RAM history is empty: a reused in-process
            # agent already holds the live turns, and re-hydrating would
            # duplicate them. Done BEFORE add_message below so the current task
            # isn't pulled in twice.
            if not self.conversation_history and len(self.conversation) > 0:
                for _m in self.conversation.get_recent_context(n=self.conversation.max_messages):
                    self.conversation_history.append({"role": _m.role, "content": _m.content})
                print(f"[DEBUG] Hydrated conversation_history from disk: {len(self.conversation_history)} messages")

            # Add current user message to conversation
            self.conversation.add_message("user", task)

            # ✅ NEW: Initialize learning modules
            self.strategy_optimizer = StrategyOptimizer(workspace)
            self.style_learner = StyleLearner(workspace)
            self.meta_learner = MetaLearner(workspace)
            yield self._log("info", "Learning modules initialized: StrategyOptimizer, StyleLearner, MetaLearner")

            # ✅ NEW: Initialize checkpoint manager
            self.checkpoint_manager = PersistentMemoryManager(workspace, checkpoint_interval=10)
            self.checkpoint_manager.register_shutdown_handler(memory)

            # Try to restore previous checkpoint
            checkpoint_info = await self.checkpoint_manager.restore_checkpoint()
            if checkpoint_info:
                yield self._log("info", f"Restored checkpoint from iteration {checkpoint_info.get('iteration_count', 0)}")

            yield self._status("running")
            # Task 5.1: mirror to EventBus (no-op when no bus is attached).
            await self._bus_status(AgentStatus.RUNNING)

            # ✅ NEW: Track task start time for learning modules
            task_start_time = time.time()

            try:  # ✅ NEW: Wrap in try-finally to ensure memory cleanup
                # ✅ FIX: Add system prompt only once at the beginning
                if not self.conversation_history:
                    system_prompt = (
                        "You are Sharrowkin, an autonomous developer agent with full access to the local workspace.\n\n"
                        "Operate with high agency:\n"
                        "- Do not ask the user follow-up questions unless the task is impossible, destructive, or requires external credentials.\n"
                        "- Infer safe defaults from the workspace, existing conventions, and conversation context.\n"
                        "- For ambiguous implementation details, choose the smallest reversible path and state the assumption in the rationale.\n"
                        "- Read/inspect relevant files before changing them; preserve public APIs and existing style.\n"
                        "- After edits, run the cheapest relevant validation commands available (tests, linters, type checkers).\n"
                        "- If validation fails, diagnose the concrete failure and choose a different fix path instead of repeating the same patch.\n"
                        "- Never include secrets or credentials in code or patches.\n\n"
                        "You have access to:\n"
                        "- Local filesystem: read, write, edit files in the workspace\n"
                        "- Terminal commands: run tests, linters, build tools, git commands\n"
                        "- AST analysis: understand code structure and dependencies\n"
                        "- Memory systems: DSM, RLD, TraceMemory for context and learning"
                    )
                    self.conversation_history.append({"role": "system", "content": system_prompt})
                    print(f"[DEBUG] Added system prompt to conversation history")

                # Store user message in conversation history
                self.conversation_history.append({"role": "user", "content": task})
                print(f"[DEBUG] Conversation history after user message: {len(self.conversation_history)} messages")

                # --- Custom Strategic Ideas Intervention ---
                task_lower = task.lower().strip()
                mutation_keywords = {
                    "создай", "напиши", "исправь", "добавь", "добавлю", "удали", "измени",
                    "сделай", "запусти", "установи", "обнови", "рефактор", "улучши", "улучшу",
                    "create", "write", "fix", "add", "delete", "remove", "change",
                    "make", "run", "install", "update", "refactor", "build", "test",
                    "deploy", "debug", "implement",
                }
                asks_for_changes = any(keyword in task_lower for keyword in mutation_keywords)
                is_strategic_request = any(
                    kw in task_lower
                    for kw in ["идеи", "развитие", "улучшение", "план действий", "nare-field", "nare field", "roadmap", "strategic"]
                ) and not asks_for_changes or (task_lower == "изучай проект" and not plan_mode == "analyze")

                if is_strategic_request:
                    strategic_response = (
                        "## 🔍 Анализ проекта Sharrowkin Agent и план улучшений\n\n"
                        "Я изучил архитектуру проекта, выявил ключевые проблемы текущей NumPy-реализации и подготовил план модернизации:\n\n"
                        "### 🏗️ Текущее состояние архитектуры\n"
                        "1. **NARE-Field (NARELabs2)**: Минимизация свободной энергии, Hopfield-подобная память Memory Field, SubQ attention ($O(N \\log N)$) и MoE-роутинг Anthill.\n"
                        "2. **DSM (Dynamic Segmented Memory)**: Векторный поиск (Dense + Sparse), термодинамическое испарение (decay) и граф памяти.\n"
                        "3. **Delta Complexity Engine**: Динамический выбор глубины рассуждений (RESONANCE, SHALLOW, DEEP, FULL).\n"
                        "4. **DPM (Dynamic Parametric Modulation)**: Динамическое роутирование и модуляция адаптеров.\n"
                        "5. **RLD (Recursive Latent DNA)**: Оркестрация инструментов и отслеживание латентных операторов.\n\n"
                        "### ⚠️ Критические проблемы\n"
                        "- 🧩 **Фрагментация**: DSM и DPM используют независимые embedding-модели (`HashEmbeddingModel` vs `HashingVectorizer`).\n"
                        "- 🔌 **Отсутствие единого API**: Модели работают автономно, усложняя построение сквозных пайплайнов.\n"
                        "- 🧪 **Слабая валидация**: Тестирование ведется в основном на искусственных примерах без оценки на реальных бенчмарках (GSM8K/MATH).\n"
                        "- ⚡ **Производительность**: Использование чистого NumPy без GPU-ускорения для вычислений полей памяти.\n\n"
                        "### 📅 План улучшений по фазам\n"
                        "#### 🔹 Фаза 1: Унификация (Недели 1-3)\n"
                        "- Создание единого интерфейса векторизации `UnifiedEmbedding`.\n"
                        "- Выравнивание схем хранения памяти DSM (`MemorySegment`) и DPM (`MemoryRecord`).\n"
                        "- Централизованная YAML/TOML конфигурация вместо разрозненных настроек.\n\n"
                        "#### 🔹 Фаза 2: Интеграция пайплайнов (Недели 4-7)\n"
                        "- Реализация единого интерфейса `SharrowkinAgent` для последовательного вызова Delta Engine -> DSM -> DPM -> NARE-Field.\n"
                        "- Добавление сквозного логирования (tracing) и поддержка асинхронного стриминга генерации.\n\n"
                        "#### 🔹 Фаза 3: Оптимизация и GPU-ускорение (Недели 8-10)\n"
                        "- Перенос вычислений MemoryField и SubQ Attention на PyTorch с поддержкой GPU.\n"
                        "- Реализация Memory-mapped storage для эффективного чтения индексов DSM.\n\n"
                        "#### 🔹 Фаза 4: Реальная валидация (Недели 11-14)\n"
                        "- Интеграция бенчмарков (GSM8K, MATH, HumanEval) и проведение систематического анализа абляции (ablation studies).\n\n"
                        "#### 🔹 Фаза 5: Production-Ready (Недели 15-19)\n"
                        "- FastAPI / gRPC интерфейс, контейнеризация и мониторинг метрик через Prometheus / Grafana.\n\n"
                        "--- \n"
                        f"📑 *Весь план улучшений успешно сохранен в файле [SHARROWKIN_IMPROVEMENT_PLAN.md](file:///{state.workspace}/SHARROWKIN_IMPROVEMENT_PLAN.md)!*"
                    )
                    self.conversation_history.append({"role": "assistant", "content": strategic_response})
                    yield {"type": "content", "content": strategic_response}
                    yield self._status("done")
                    await self._bus_status(AgentStatus.DONE, include_runtime=True)
                    await self._bus_agent_complete(AgentOutcome.DONE)
                    return

                # --- Intent Routing ---
                try:
                    if plan_mode == "analyze":
                        intent = {"is_informational": True, "is_conversational": False}
                        print(f"[AGENT] Overriding intent to informational for plan_mode=analyze")
                    else:
                        intent = await retry_async(
                            lambda: self.gemini.classify_intent(task),
                            policy=LLM_RETRY_POLICY,
                        )
                    print(f"[AGENT] Intent result: {intent}")
                    if intent.get("is_conversational"):
                        response = intent.get("response")
                        if not response:
                            if not self.gemini.configured:
                                # Get agent name from persona
                                from personas import get_agent_name
                                agent_name = get_agent_name()
                                response = f"Привет! Я {agent_name} — автономный агент-разработчик. Чем могу помочь?"
                            else:
                                try:
                                    # Build conversation context for LLM
                                    history_text = self._format_history()
                                    prompt = f"{history_text}\n\nUser: {task}" if history_text else task
                                    # Inject persona into system instruction - persona REPLACES base instruction
                                    base_instruction = (
                                        f"{AUTONOMOUS_AGENT_POLICY}\n\n"
                                    )

                                    # Add selected repository context if available
                                    if state.selected_repo:
                                        base_instruction += (
                                            f"\n\nCURRENT REPOSITORY: {state.selected_repo}\n"
                                            f"The user has selected this repository for work. "
                                            f"When discussing code or files, assume they are in this repository.\n\n"
                                        )
                                    else:
                                        base_instruction += (
                                            "\n\nNO REPOSITORY SELECTED YET\n"
                                            "If the user asks about code or wants to make changes, "
                                            "you should ask them to select a repository first.\n\n"
                                        )

                                    base_instruction += (
                                        "You have access to the conversation history above. "
                                        "Respond naturally and helpfully to the user's latest message. "
                                        "If the user asks for a concrete action, say what you will do instead of asking for unnecessary confirmation. "
                                        "Keep it concise and friendly. Answer in the same language the user writes in."
                                    )
                                    system_instruction = inject_persona(base_instruction)

                                    response = await asyncio.wait_for(
                                        retry_async(
                                            lambda: self.gemini.generate_text(
                                                prompt,
                                                system_instruction
                                            ),
                                            policy=LLM_RETRY_POLICY,
                                        ),
                                        timeout=20,
                                    )
                                except Exception as exc:
                                    print(f"[AGENT] LLM response generation failed: {exc}")
                                    from personas import get_agent_name
                                    agent_name = get_agent_name()
                                    response = f"Привет! Я {agent_name} — автономный агент-разработчик. Чем могу помочь?"
                        # Store assistant response
                        self.conversation_history.append({"role": "assistant", "content": response})
                        # Also persist to the disk-backed conversation so the
                        # reply survives a restart (the user turn was already
                        # saved above when self.conversation.add_message ran).
                        if self.conversation:
                            self.conversation.add_message("assistant", response)
                        # Keep history manageable (last 20 messages)
                        if len(self.conversation_history) > 20:
                            self.conversation_history = self.conversation_history[-20:]
                        yield {"type": "content", "content": response}
                        yield self._status("done")
                        await self._bus_status(AgentStatus.DONE, include_runtime=True)
                        await self._bus_agent_complete(AgentOutcome.DONE)
                        return
                except Exception as exc:
                    print(f"[AGENT] Intent classification error: {exc}")

                # --- Informational / Read-Only Flow ---
                if intent.get("is_informational"):
                    yield self._log("system", "Informational analysis cycle started.")

                    try:
                        # Check if this is a GitHub API request (skip local workspace scan)
                        is_github_request = any(keyword in state.task.lower() for keyword in [
                            "репозитори", "репо", "repository", "repositories", "github",
                            "список репо", "мои репо", "какие репо", "где мои репо"
                        ])

                        print(f"[DEBUG] Task: {state.task}")
                        print(f"[DEBUG] Task lower: {state.task.lower()}")
                        print(f"[DEBUG] is_github_request: {is_github_request}")

                        if not is_github_request:
                            # 1. Observe Phase (AST Scan) - only for local workspace queries
                            with self._tracer.start_as_current_span("phase_observe"):
                                async for event in self._observe(state, memory):
                                    yield event

                            # 2. Recall Phase (Memory Retrieval)
                            with self._tracer.start_as_current_span("phase_recall"):
                                async for event in self._recall(state, memory):
                                    yield event
                        else:
                            # For GitHub requests, skip workspace scan
                            yield self._log("info", "GitHub API request detected - skipping local workspace scan")

                        # 3. Reason Phase (Rich response generation)
                        with self._tracer.start_as_current_span("phase_reason"):
                            yield self._phase("Reason", "active")
                            yield self._log("info", "Generating response...")

                            try:
                                if is_github_request:
                                    # For GitHub requests, call the appropriate tool directly
                                    from config import SETTINGS

                                    # Check if we have a GitHub token
                                    if not SETTINGS.github_token:
                                        error_msg = "❌ GitHub не подключен. Пожалуйста, подключите GitHub в настройках."
                                        yield {"type": "content", "content": error_msg}
                                        # ✅ SAVE AGENT RESPONSE TO CONVERSATION HISTORY
                                        self.conversation_history.append({"role": "assistant", "content": error_msg})
                                        if len(self.conversation_history) > 20:
                                            self.conversation_history = self.conversation_history[-20:]
                                        yield self._status("done")
                                        await self._bus_status(AgentStatus.DONE, include_runtime=True)
                                        await self._bus_agent_complete(AgentOutcome.DONE)
                                        return

                                    # Call github_list_repos tool
                                    yield self._log("info", "Calling GitHub API to list repositories...")
                                    try:
                                        repos_json = await github_list_repos(SETTINGS.github_token)

                                        # Parse and format the response
                                        import json

                                        # ✅ FIX: Check if repos_json is empty or invalid
                                        if not repos_json or not repos_json.strip():
                                            print("[AGENT] github_list_repos returned empty response")
                                            repos = []
                                        else:
                                            try:
                                                repos = json.loads(repos_json)
                                            except json.JSONDecodeError as e:
                                                print(f"[AGENT] Failed to parse repos JSON: {e}")
                                                print(f"[AGENT] repos_json: {repos_json[:200]}")
                                                repos = []

                                        if isinstance(repos, list) and len(repos) > 0:
                                            response = "📦 **Ваши GitHub репозитории:**\n\n"
                                            for repo in repos:
                                                name = repo.get("full_name", repo.get("name", "Unknown"))
                                                desc = repo.get("description", "Нет описания")
                                                url = repo.get("url", "")
                                                lang = repo.get("language", "")
                                                stars = repo.get("stars", 0)
                                                private = "🔒 Private" if repo.get("private") else "🌐 Public"

                                                response += f"### {name}\n"
                                                response += f"- {private}\n"
                                                if desc:
                                                    response += f"- 📝 {desc}\n"
                                                if lang:
                                                    response += f"- 💻 {lang}\n"
                                                if stars > 0:
                                                    response += f"- ⭐ {stars} stars\n"
                                                response += f"- 🔗 {url}\n\n"

                                            state.last_rationale = response
                                        else:
                                            state.last_rationale = "У вас пока нет репозиториев на GitHub."
                                    except Exception as e:
                                        state.last_rationale = f"❌ Ошибка при получении списка репозиториев: {str(e)}"
                                else:
                                    # For local workspace queries, provide full context
                                    import os
                                    # Read README.md if it exists in the workspace
                                    readme_content = ""
                                    readme_path = os.path.join(state.workspace, "README.md")
                                    if os.path.exists(readme_path):
                                        try:
                                            with open(readme_path, "r", encoding="utf-8") as rf:
                                                readme_content = rf.read(12000)
                                        except Exception:
                                            pass

                                    # Clip AST summary to avoid proxy timeout
                                    ws_summary_clipped = state.workspace_summary or ""
                                    if len(ws_summary_clipped) > 8000:
                                        ws_summary_clipped = ws_summary_clipped[:8000] + "\n... [truncated for brevity] ..."

                                    # ✅ ADD CONVERSATION HISTORY
                                    conversation_context = self._format_history()

                                    # ✅ FIX: Build rich context with workspace summary and memory
                                    rich_prompt = f"User request: {state.task}\n\n"

                                    if conversation_context:
                                        rich_prompt += f"{conversation_context}\n\n"

                                    if readme_content:
                                        rich_prompt += f"## Workspace README.md:\n{readme_content}\n\n"

                                    if ws_summary_clipped:
                                        rich_prompt += f"## Workspace Structure (AST Analysis):\n{ws_summary_clipped}\n\n"

                                    if state.memory_context:
                                        rich_prompt += f"## Memory Context (DSM/RLD/TraceMemory):\n{state.memory_context}\n\n"

                                    rich_prompt += (
                                        "Please analyze the workspace and answer the user's request thoroughly. "
                                        "Use the workspace structure, README, and memory context to provide a detailed, accurate response. "
                                        "Structure your reply with markdown headers and bullet points. "
                                        "Answer in the same language as the user query (usually Russian)."
                                    )

                                # ✅ FIX: Use proper system instruction without GitHub-only policy
                                rich_response = await retry_async(
                                    lambda: self.gemini.generate_text(
                                        rich_prompt,
                                        inject_persona(
                                            "You are Sharrowkin, an autonomous developer agent analyzing a local codebase. "
                                            "You have access to the workspace structure, README, and memory context. "
                                            "Provide professional, detailed analysis based on the provided context. "
                                            "Use markdown formatting and answer in the user's language."
                                        )
                                    ),
                                    policy=LLM_RETRY_POLICY,
                                )
                                state.last_rationale = rich_response
                            except Exception as exc:
                                print(f"[AGENT] Rich response generation failed: {exc}")
                                state.last_rationale = f"Не удалось сгенерировать ответ: {exc}"

                            yield self._phase("Reason", "done")

                        if state.last_rationale:
                            yield {"type": "content", "content": state.last_rationale}
                            # ✅ SAVE AGENT RESPONSE TO CONVERSATION HISTORY
                            self.conversation_history.append({"role": "assistant", "content": state.last_rationale})
                            print(f"[DEBUG] Saved assistant response to conversation_history. Total messages: {len(self.conversation_history)}")
                            print(f"[DEBUG] Last 3 messages: {[(m['role'], m['content'][:50]) for m in self.conversation_history[-3:]]}")
                            # Keep history manageable (last 20 messages)
                            if len(self.conversation_history) > 20:
                                self.conversation_history = self.conversation_history[-20:]

                            # ✅ ASK LLM TO SUMMARIZE INFORMATIONAL ANALYSIS
                            if self.gemini.configured:
                                try:
                                    # Detect user language from task
                                    is_russian = any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in state.task)

                                    if is_russian:
                                        summary_prompt = f"""Ты только что проанализировал проект и ответил на вопрос пользователя. Подведи итоги своей работы.

Вопрос пользователя: {state.task}

Твой анализ:
{state.last_rationale[:1000] if state.last_rationale else 'Анализ выполнен'}

Напиши краткий отчёт (2-3 предложения) о том, что ты проанализировал и какой ответ дал.
Используй формат:
## ✅ Анализ завершён
[твой отчёт]"""
                                        system_msg = "Ты Sharrowkin агент. Подведи итоги своего анализа кратко и по делу."
                                    else:
                                        summary_prompt = f"""You just analyzed the project and answered the user's question. Summarize your work.

User question: {state.task}

Your analysis:
{state.last_rationale[:1000] if state.last_rationale else 'Analysis completed'}

Write a brief report (2-3 sentences) about what you analyzed and what answer you provided.
Use format:
## ✅ Analysis Complete
[your report]"""
                                        system_msg = "You are Sharrowkin agent. Summarize your analysis briefly and to the point."

                                    summary = await retry_async(
                                        lambda: self.gemini.generate_text(
                                            summary_prompt,
                                            system_msg
                                        ),
                                        policy=LLM_RETRY_POLICY,
                                    )

                                    yield {"type": "content", "content": summary}
                                    # ✅ SAVE SUMMARY TO CONVERSATION HISTORY
                                    self.conversation_history.append({"role": "assistant", "content": summary})
                                    if len(self.conversation_history) > 20:
                                        self.conversation_history = self.conversation_history[-20:]
                                except Exception as e:
                                    print(f"[AGENT] Summary generation failed: {e}")
                                    # Fallback to simple message
                                    is_russian = any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in state.task)
                                    if is_russian:
                                        fallback = f"## ✅ Анализ завершён\n\nПроанализировал проект и ответил на вопрос: {state.task}"
                                    else:
                                        fallback = f"## ✅ Analysis Complete\n\nAnalyzed the project and answered the question: {state.task}"
                                    yield {"type": "content", "content": fallback}
                                    self.conversation_history.append({"role": "assistant", "content": fallback})
                            else:
                                # No LLM configured - use simple summary
                                is_russian = any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in state.task)
                                if is_russian:
                                    fallback = f"## ✅ Анализ завершён\n\nПроанализировал проект и ответил на вопрос: {state.task}"
                                else:
                                    fallback = f"## ✅ Analysis Complete\n\nAnalyzed the project and answered the question: {state.task}"
                                yield {"type": "content", "content": fallback}
                                self.conversation_history.append({"role": "assistant", "content": fallback})

                            yield self._status("done")
                            yield self._log("success", "Informational analysis completed.")
                            await self._bus_status(AgentStatus.DONE, include_runtime=True)
                            await self._bus_agent_complete(AgentOutcome.DONE)
                            return
                    except Exception as e:
                        print(f"[AGENT] Informational loop error: {e}")
                        yield self._status("error", message=str(e))
                        await self._bus_status(AgentStatus.ERROR, message=str(e), include_runtime=True)
                        await self._bus_agent_complete(AgentOutcome.ERROR)
                        return

                # --- Full coding agent cycle ---
                yield self._log("system", "Cognitive cycle started.")

                try:
                    # The agent operates directly on the local workspace. It no
                    # longer interrupts coding tasks to demand a GitHub repo
                    # selection — work proceeds in the active workspace.

                    with self._tracer.start_as_current_span("phase_observe"):
                        # Task 5.2: wrap Observe in PhaseGuard. Non-critical
                        # phase — on error we continue to Recall.
                        observe_events, observe_outcome = await self._run_phase_guarded(
                            PhaseId.OBSERVE, self._observe(state, memory)
                        )
                        for event in observe_events:
                            yield event
                        # ✅ NEW: Log memory after Observe phase
                        self.memory_profiler.log_snapshot(f"After Observe")
                        if observe_outcome in ("error", "timeout"):
                            yield self._log("warning", f"Observe phase failed ({observe_outcome}), continuing...")

                    # Task 5.6: Track phase statuses for Checkpoint v2
                    _phase_statuses: dict[PhaseId, PhaseStatus] = {pid: PhaseStatus.PENDING for pid in PhaseId}
                    _phase_statuses[PhaseId.OBSERVE] = PhaseStatus.DONE if observe_outcome == "ok" else PhaseStatus.ERROR
                    _checkpoint_session_id = session_id
                    _current_checkpoint_phase: list[PhaseId] = [PhaseId.OBSERVE]  # mutable for closure

                    # Task 5.6: Save checkpoint after Observe
                    if observe_outcome == "ok":
                        await self._save_checkpoint_v2(state, memory, PhaseId.OBSERVE, _phase_statuses, _checkpoint_session_id)

                    # Task 5.6: Start background 60-second checkpoint timer
                    _checkpoint_timer_running = True

                    async def _periodic_checkpoint_save():
                        """Background task: save checkpoint every 60 seconds."""
                        while _checkpoint_timer_running:
                            await asyncio.sleep(60)
                            if not _checkpoint_timer_running:
                                break
                            try:
                                await self._save_checkpoint_v2(
                                    state, memory, _current_checkpoint_phase[0], _phase_statuses, _checkpoint_session_id
                                )
                            except Exception as e:
                                print(f"[AGENT][Checkpoint v2] Periodic save failed: {e}")

                    _checkpoint_timer_task = asyncio.create_task(_periodic_checkpoint_save())

                    with self._tracer.start_as_current_span("phase_recall"):
                        # Task 5.2: wrap Recall in PhaseGuard. Non-critical
                        # phase — on error we continue to Reason.
                        recall_events, recall_outcome = await self._run_phase_guarded(
                            PhaseId.RECALL, self._recall(state, memory)
                        )
                        for event in recall_events:
                            yield event
                        # ✅ NEW: Log memory after Recall phase
                        self.memory_profiler.log_snapshot(f"After Recall")
                        if recall_outcome in ("error", "timeout"):
                            yield self._log("warning", f"Recall phase failed ({recall_outcome}), continuing...")

                    # Task 5.6: Update phase status and save checkpoint after Recall
                    _phase_statuses[PhaseId.RECALL] = PhaseStatus.DONE if recall_outcome == "ok" else PhaseStatus.ERROR
                    _current_checkpoint_phase[0] = PhaseId.RECALL
                    if recall_outcome == "ok":
                        await self._save_checkpoint_v2(state, memory, PhaseId.RECALL, _phase_statuses, _checkpoint_session_id)

                    success = False
                    # --- ReAct tool-calling loop (replaces the old one-shot
                    # _reason → _stabilize iteration block). The model now calls
                    # tools one at a time and reacts to real results, instead of
                    # emitting one giant JSON patch it could fake. See
                    # agent/tool_loop.py. The old _reason/_stabilize methods are
                    # kept (deprecated) for the checkpoint-resume path.
                    with self._tracer.start_as_current_span("phase_reason"):
                        # Generate a hierarchical plan (non-fatal) and surface it
                        # to the UI + inject it into the loop's initial context so
                        # the agent actually follows a plan.
                        plan_text = await self._generate_plan(state)

                        hook_runner = self._build_hook_runner(state.workspace)
                        toolbox = AgentToolbox(
                            state.workspace,
                            gemini=self.gemini,
                            hook_runner=hook_runner,
                        )
                        loop = ToolLoop(
                            self.gemini,
                            toolbox,
                            max_steps=self.max_iterations,
                            max_extensions=self.config.execution.max_extensions,
                        )
                        initial_context = self._build_loop_context(state, plan_text)
                        try:
                            async for event in loop.run(
                                state.task,
                                initial_context,
                                ui_delays_enabled=self.config.execution.ui_delays_enabled,
                            ):
                                yield event
                        except Exception as exc:
                            await self._safe_learn_failure(
                                memory, task=state.task,
                                states=state.states, actions=loop.actions,
                                error_message=str(exc), tools_used=loop.tools_used,
                                changed_files=loop.changed_files,
                            )
                            yield self._log("error", f"Tool loop crashed: {exc}")
                            loop.success = False
                            loop.final_summary = f"Tool loop crashed: {exc}"

                        # Mirror loop results onto AgentRunState so the
                        # summary/commit code below sees them unchanged.
                        success = loop.success
                        state.actions = loop.actions
                        state.tools_used = loop.tools_used
                        state.current_changed_files = loop.changed_files
                        state.changes_made = bool(loop.changed_files)
                        state.final_diff = loop.final_diff
                        state.last_rationale = loop.final_summary
                        if not success and loop.final_summary:
                            state.last_error = loop.final_summary

                        self.memory_profiler.log_snapshot("After tool loop")

                        _phase_statuses[PhaseId.REASON] = PhaseStatus.DONE if success else PhaseStatus.ERROR
                        _phase_statuses[PhaseId.STABILIZE] = PhaseStatus.DONE if success else PhaseStatus.ERROR
                        _current_checkpoint_phase[0] = PhaseId.STABILIZE
                        await self._save_checkpoint_v2(state, memory, PhaseId.STABILIZE, _phase_statuses, _checkpoint_session_id)

                        if not success:
                            await self._safe_learn_failure(
                                memory, task=state.task,
                                states=state.states, actions=state.actions,
                                error_message=state.last_error or "tool loop did not complete",
                                tools_used=state.tools_used,
                                changed_files=state.current_changed_files,
                            )

                    if success:
                        # Task 5.2: wrap Commit in PhaseGuard. Critical
                        # phase — on error we report error status.
                        commit_events, commit_outcome = await self._run_phase_guarded(
                            PhaseId.COMMIT, self._commit(state, memory)
                        )
                        for event in commit_events:
                            yield event
                        # ✅ NEW: Log memory after Commit phase
                        self.memory_profiler.log_snapshot(f"After Commit")

                        if commit_outcome in ("error", "timeout"):
                            yield self._log("error", f"Commit phase failed ({commit_outcome}).")
                            _phase_statuses[PhaseId.COMMIT] = PhaseStatus.ERROR
                            # Fall through to the error path below
                            success = False
                        else:
                            # Task 5.6: Commit succeeded — update status and save final checkpoint
                            _phase_statuses[PhaseId.COMMIT] = PhaseStatus.DONE
                            _current_checkpoint_phase[0] = PhaseId.COMMIT
                            await self._save_checkpoint_v2(state, memory, PhaseId.COMMIT, _phase_statuses, _checkpoint_session_id)

                    if success:

                        # ✅ ASK LLM TO SUMMARIZE ITS OWN WORK
                        if self.gemini.configured:
                            try:
                                # Detect user language from task
                                is_russian = any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in state.task)

                                if is_russian:
                                    summary_prompt = f"""Ты только что выполнил задачу. Подведи итоги своей работы.

Задача: {state.task}

Что было сделано:
{chr(10).join(f"- {action}" for action in state.actions)}

Изменённые файлы: {', '.join(state.current_changed_files) if state.current_changed_files else 'нет'}

Использованные инструменты: {', '.join(list(dict.fromkeys(state.tools_used)))}

Результат работы:
{state.last_rationale if state.last_rationale else 'Изменения применены'}

Напиши краткий отчёт (2-4 предложения) о том, что ты сделал и какой результат получился.
Используй формат:
## ✅ Задача выполнена
[твой отчёт]"""
                                    system_msg = "Ты Sharrowkin агент. Подведи итоги своей работы кратко и по делу."
                                else:
                                    summary_prompt = f"""You just completed a task. Summarize your work.

Task: {state.task}

What was done:
{chr(10).join(f"- {action}" for action in state.actions)}

Changed files: {', '.join(state.current_changed_files) if state.current_changed_files else 'none'}

Tools used: {', '.join(list(dict.fromkeys(state.tools_used)))}

Result:
{state.last_rationale if state.last_rationale else 'Changes applied'}

Write a brief report (2-4 sentences) about what you did and what result you achieved.
Use format:
## ✅ Task Complete
[your report]"""
                                    system_msg = "You are Sharrowkin agent. Summarize your work briefly and to the point."

                                summary = await retry_async(
                                    lambda: self.gemini.generate_text(
                                        summary_prompt,
                                        system_msg
                                    ),
                                    policy=LLM_RETRY_POLICY,
                                )

                                yield {"type": "content", "content": summary}
                                # ✅ SAVE SUMMARY TO CONVERSATION HISTORY
                                self.conversation_history.append({"role": "assistant", "content": summary})
                                if len(self.conversation_history) > 20:
                                    self.conversation_history = self.conversation_history[-20:]
                            except Exception as e:
                                print(f"[AGENT] Summary generation failed: {e}")
                                # Fallback to simple message
                                is_russian = any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in state.task)
                                if is_russian:
                                    fallback = f"## ✅ Задача выполнена\n\n{state.last_rationale if state.last_rationale else 'Изменения применены успешно.'}"
                                else:
                                    fallback = f"## ✅ Task Complete\n\n{state.last_rationale if state.last_rationale else 'Changes applied successfully.'}"
                                yield {"type": "content", "content": fallback}
                                self.conversation_history.append({"role": "assistant", "content": fallback})
                        else:
                            # No LLM configured - use simple summary
                            is_russian = any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in state.task)
                            if is_russian:
                                fallback = f"## ✅ Задача выполнена\n\n{state.last_rationale if state.last_rationale else 'Изменения применены успешно.'}"
                            else:
                                fallback = f"## ✅ Task Complete\n\n{state.last_rationale if state.last_rationale else 'Changes applied successfully.'}"
                            yield {"type": "content", "content": fallback}
                            self.conversation_history.append({"role": "assistant", "content": fallback})
                            simple_summary = f"## ✅ Задача выполнена\n\nИзменено файлов: {len(state.current_changed_files)}"
                            yield {"type": "content", "content": simple_summary}
                            self.conversation_history.append({"role": "assistant", "content": simple_summary})

                        yield self._status("done")
                        yield self._log("success", "Task stabilized and stored in local memory.")
                        await self._bus_status(AgentStatus.DONE, include_runtime=True)
                        await self._bus_agent_complete(AgentOutcome.DONE)
                    else:
                        # ✅ NEW: Record failure in TraceMemory for learning
                        if state.last_error:
                            await self._safe_learn_failure(
                                memory,
                                task=state.task,
                                states=state.states,
                                actions=state.actions,
                                error_message=state.last_error,
                                tools_used=state.tools_used,
                                changed_files=state.current_changed_files
                            )

                            error_msg = f"⚠️ **Self-healing loop reached the iteration limit.**\n\nLast error:\n```log\n{state.last_error}\n```"
                            yield {"type": "content", "content": error_msg}
                            # ✅ SAVE AGENT RESPONSE TO CONVERSATION HISTORY
                            self.conversation_history.append({"role": "assistant", "content": error_msg})
                            if len(self.conversation_history) > 20:
                                self.conversation_history = self.conversation_history[-20:]
                        yield self._status("error")
                        yield self._log("error", "Self-healing loop reached the iteration limit.")
                        await self._bus_status(
                            AgentStatus.ERROR,
                            message="self-healing loop reached the iteration limit",
                            include_runtime=True,
                        )
                        await self._bus_agent_complete(AgentOutcome.ERROR)
                except GeminiConfigurationError as exc:
                    yield self._phase("Reason", "error")
                    yield self._thinking(f"API key not configured: {exc}")
                    api_error_msg = f"⚠️ **API ключ не настроен.**\n\nДобавьте `GEMINI_API_KEY` в файл `backend/backend/.env` для работы с кодом.\n\n```\n{exc}\n```"
                    yield {"type": "content", "content": api_error_msg}
                    # ✅ SAVE AGENT RESPONSE TO CONVERSATION HISTORY
                    self.conversation_history.append({"role": "assistant", "content": api_error_msg})
                    if len(self.conversation_history) > 20:
                        self.conversation_history = self.conversation_history[-20:]
                    yield self._status("needs_key")
                    yield self._log("error", str(exc))
                    # Task 5.1: ``needs_key`` has no canonical AgentStatus
                    # equivalent yet (the bus enum is the public contract).
                    # We surface it as ERROR + agent_complete(error) on the
                    # bus so UI clients on the new contract still see the
                    # terminal transition; the legacy ``needs_key`` value is
                    # preserved on the dict channel for the existing UI.
                    await self._bus_status(
                        AgentStatus.ERROR,
                        message=f"api_key_not_configured: {exc}",
                        include_runtime=True,
                    )
                    await self._bus_agent_complete(AgentOutcome.ERROR)
                except Exception as exc:
                    await self.plugins.run_on_error(state, exc)
                    print(f"[AGENT] Cycle error: {exc}")

                    # ✅ NEW: Record exception in TraceMemory for learning
                    await self._safe_learn_failure(
                        memory,
                        task=state.task,
                        states=state.states,
                        actions=state.actions,
                        error_message=str(exc),
                        tools_used=state.tools_used,
                        changed_files=state.current_changed_files
                    )

                    yield self._thinking(f"Error: {exc}")
                    general_error_msg = f"⚠️ **Ошибка агента:**\n\n```\n{exc}\n```"
                    yield {"type": "content", "content": general_error_msg}
                    # ✅ SAVE AGENT RESPONSE TO CONVERSATION HISTORY
                    self.conversation_history.append({"role": "assistant", "content": general_error_msg})
                    if len(self.conversation_history) > 20:
                        self.conversation_history = self.conversation_history[-20:]
                    yield self._status("error")
                    yield self._log("error", f"Agent cycle failed: {exc}")
                    await self._bus_status(
                        AgentStatus.ERROR,
                        message=f"agent_cycle_failed: {exc}",
                        include_runtime=True,
                    )
                    await self._bus_agent_complete(AgentOutcome.ERROR)
            finally:
                # Task 5.6: Cancel the periodic checkpoint timer
                try:
                    if '_checkpoint_timer_task' in locals() and _checkpoint_timer_task is not None:
                        _checkpoint_timer_running = False
                        _checkpoint_timer_task.cancel()
                        try:
                            await _checkpoint_timer_task
                        except (asyncio.CancelledError, Exception):
                            pass
                except Exception:
                    pass

                # Task 5.7: Guarantee agent_complete is always emitted.
                # Determine final outcome based on what happened in the run.
                # If agent_complete was already emitted by the normal flow,
                # this is a safety net for unexpected exceptions that bypass
                # all normal exit paths.
                _final_outcome = AgentOutcome.ERROR  # default to error
                if 'success' in locals() and success:
                    _final_outcome = AgentOutcome.DONE
                # Note: AgentOutcome.STOPPED would be set if cancellation
                # was detected, but that's handled by CancelledError propagation.
                await self._bus_agent_complete(_final_outcome)

                # ✅ NEW: Always cleanup memory resources
                if memory:
                    # Save final checkpoint before closing
                    if self.checkpoint_manager:
                        try:
                            await self.checkpoint_manager.save_checkpoint(memory)
                            print(f"[Checkpoint] Final checkpoint saved")
                        except Exception as e:
                            print(f"[Checkpoint] Error saving final checkpoint: {e}")

                    memory.close()
                    print(f"[AGENT] Memory resources closed")
                # Log final memory stats
                self.memory_profiler.log_snapshot("Agent run completed")
                stats = self.memory_profiler.get_stats()
                print(f"[AGENT] Final memory stats: {stats}")

    # --- Phase: Observe -----------------------------------------------------
    async def _observe(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
    ) -> AsyncIterator[dict[str, object]]:
        yield self._phase("Observe", "active")
        await self.plugins.run_pre_observe(state)
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Observe"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }

        # Try to load from cache first
        cached = self.workspace_cache.get(state.workspace)

        if cached:
            # Cache hit - use cached data
            cache_age = int(cached.age_seconds())
            yield self._log("info", f"Using cached workspace scan (age: {cache_age}s, {cached.total_files} files)")
            yield self._tool_call("scan_workspace", status="done", target=str(state.workspace), detail=f"[CACHED] {cached.total_files} files, {cached.total_lines} lines")

            state.workspace_summary = cached.workspace_summary
            state.complexity_avg = cached.complexity_avg
            state.circular_dependencies = cached.circular_dependencies
            state.most_complex_functions = cached.most_complex_functions

            # Append semantic insights to workspace summary
            state.workspace_summary += cached.semantic_insights

            state.actions.append(f"Loaded cached workspace scan ({cached.total_files} files)")
            state.tools_used.append("workspace_cache")

            yield self._phase("Observe", "done")
            return

        # Cache miss - perform full scan
        yield self._log("info", f"Scanning workspace: {state.workspace}")
        yield self._tool_call("scan_workspace", status="running", target=str(state.workspace))
        await asyncio.sleep(0.3) if self.config.execution.ui_delays_enabled else await asyncio.sleep(0)  # Small delay to show tool is working
        summaries = await asyncio.to_thread(scan_workspace, state.workspace)
        total_lines = sum(summary.line_count for summary in summaries)
        state.workspace_summary = summarize_workspace(summaries)
        await asyncio.sleep(0.2 if self.config.execution.ui_delays_enabled else 0)
        yield self._tool_call("scan_workspace", status="done", target=str(state.workspace), detail=f"{len(summaries)} files, {total_lines} lines")
        state.actions.append(f"Scanned {len(summaries)} source files with AST summaries")
        state.tools_used.append("pathlib")
        state.tools_used.append("ast")
        
        # Build Semantic Graph and Analyze Dependencies
        try:
            yield self._tool_call("analyze_dependencies", status="running", target=str(state.workspace))
            await asyncio.sleep(0.3)
            dep_analyzer = DependencyAnalyzer()
            await asyncio.to_thread(dep_analyzer.analyze_directory, state.workspace)
            dep_graph = dep_analyzer.get_graph()

            sem_graph = SemanticGraph(state.workspace / ".sharrowkin" / "semantic_graph")
            sem_builder = SemanticGraphBuilder(sem_graph)
            await asyncio.to_thread(sem_builder.build_from_directory, state.workspace)
            await asyncio.to_thread(sem_graph.save_to_dsm)

            metrics = sem_graph.calculate_complexity_metrics()
            circular = dep_graph.get_circular_dependencies()

            state.complexity_avg = round(metrics.get("average_complexity", 1.0), 2)
            state.circular_dependencies = len(circular)
            state.most_complex_functions = metrics.get("most_complex", [])

            # Aggregate semantic insights for the agent context
            patterns = sem_graph.get_detected_patterns()
            patterns_str = ""
            for pattern_name, class_ids in patterns.items():
                if class_ids:
                    patterns_str += f"  - {pattern_name}: {', '.join(class_ids[:10])}\n"
            
            git_hotspots_str = ""
            if sem_graph.git_hotspots:
                git_hotspots_str += "\nGit Hotspots (most modified files):\n"
                for file_path, count in sem_graph.git_hotspots[:5]:
                    git_hotspots_str += f"  - {file_path} (changed {count} times)\n"
            
            recent_commits_str = ""
            if sem_graph.recent_commits:
                recent_commits_str += "\nRecent Commits:\n"
                for commit in sem_graph.recent_commits[:5]:
                    recent_commits_str += f"  - {commit['hash']} by {commit['author']}: {commit['message']} ({commit['date']})\n"
            
            doc_links_str = ""
            doc_linked_nodes = [n for n in sem_graph.nodes.values() if "doc_links" in n.metadata]
            if doc_linked_nodes:
                doc_links_str += "\nDocumentation Links:\n"
                for node in doc_linked_nodes[:10]:
                    links = [f"{link['title']} ({link['path']})" for link in node.metadata["doc_links"]]
                    doc_links_str += f"  - {node.id} -> {', '.join(links)}\n"

            # Phase 3: Deep Code Understanding with Context Linker and Data Flow
            phase3_insights = ""
            try:
                from analysis.code.context_linker import ContextLinker
                from analysis.code.data_flow_analyzer import DataFlowAnalyzer

                linker = ContextLinker(sem_graph, state.workspace)
                flow_analyzer = DataFlowAnalyzer(sem_graph)

                # Analyze top 5 most complex functions with enriched context
                complex_funcs = metrics.get("most_complex", [])[:5]
                if complex_funcs:
                    phase3_insights += "\n\nPhase 3 Deep Analysis (Context + Data Flow):\n"
                    for func_info in complex_funcs:
                        func_id = func_info["id"]

                        # Get enriched context
                        enriched = sem_graph.get_enriched_context(func_id, state.workspace)
                        if "error" not in enriched:
                            phase3_insights += f"\n  Function: {func_id} (complexity: {func_info['complexity']})\n"

                            # Context info
                            if "context" in enriched:
                                ctx = enriched["context"]
                                if ctx.get("git_history", {}).get("change_frequency", 0) > 0:
                                    phase3_insights += f"    - Git: Modified {ctx['git_history']['change_frequency']} times\n"
                                if ctx.get("relationships", {}).get("callers"):
                                    phase3_insights += f"    - Called by: {', '.join(ctx['relationships']['callers'][:3])}\n"
                                if ctx.get("test_coverage", 0) > 0:
                                    phase3_insights += f"    - Test coverage: {ctx['test_coverage']:.0f}%\n"

                            # Data flow issues
                            if "data_flow" in enriched:
                                df = enriched["data_flow"]
                                if df.get("issues"):
                                    phase3_insights += f"    - Data flow issues: {len(df['issues'])} found\n"
                                    for issue in df["issues"][:2]:
                                        phase3_insights += f"      • {issue['severity']}: {issue['message']}\n"

                # Store semantic graph reference for later use
                state.semantic_graph = sem_graph

            except Exception as e:
                print(f"[AGENT] Phase 3 analysis failed (non-fatal): {e}")

            semantic_insights = (
                "\n\n=========================================\n"
                "SEMANTIC CODE INSIGHTS (Phase 2 + Phase 3)\n"
                "=========================================\n"
            )
            if patterns_str:
                semantic_insights += f"Detected Design Patterns:\n{patterns_str}"
            if git_hotspots_str:
                semantic_insights += git_hotspots_str
            if recent_commits_str:
                semantic_insights += recent_commits_str
            if doc_links_str:
                semantic_insights += doc_links_str
            if phase3_insights:
                semantic_insights += phase3_insights

            state.workspace_summary += semantic_insights
            await asyncio.sleep(0.2 if self.config.execution.ui_delays_enabled else 0)
            yield self._tool_call("analyze_dependencies", status="done", target=str(state.workspace), detail=f"complexity={state.complexity_avg}, circular={state.circular_dependencies}")

            # Cache the scan results for future queries
            latest_mtime = max(
                (f.stat().st_mtime for f in state.workspace.rglob("*.py") if f.is_file()),
                default=time.time()
            )
            self.workspace_cache.set(
                state.workspace,
                CachedWorkspace(
                    workspace_summary=state.workspace_summary,
                    total_files=len(summaries),
                    total_lines=total_lines,
                    complexity_avg=state.complexity_avg,
                    circular_dependencies=state.circular_dependencies,
                    most_complex_functions=state.most_complex_functions,
                    semantic_insights=semantic_insights,
                    timestamp=time.time(),
                    last_mtime=latest_mtime,
                )
            )

        except Exception as e:
            print(f"[AGENT] Code analysis failed: {e}")
            state.complexity_avg = 1.0
            state.circular_dependencies = 0
            state.most_complex_functions = []

        state.states.append(state.workspace_summary)
        file_list = [s.path for s in summaries[:15]]
        await self._safe_learn_project(memory, state.workspace_summary)
        yield {
            "type": "project_intelligence",
            "status": "ready",
            "workspace_path": str(state.workspace),
            "files_indexed": len(summaries),
            "lines_indexed": total_lines,
            "symbols": sum(len(summary.symbols) for summary in summaries),
            "complexity_avg": state.complexity_avg,
            "circular_dependencies": state.circular_dependencies,
            "most_complex_functions": state.most_complex_functions,
            "summary": f"Explored {len(summaries)} files, {total_lines} lines",
        }
        yield self._tool_activity(
            f"Explored {len(summaries)} files, {total_lines} lines",
            message=", ".join(file_list[:5]) + ("…" if len(file_list) > 5 else ""),
            target=str(state.workspace),
        )
        yield self._log("success", f"Observed {len(summaries)} source files.")
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Observe"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        await self.plugins.run_post_observe(state)
        yield self._phase("Observe", "done")

    # --- Phase: Recall ------------------------------------------------------
    async def _recall(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
    ) -> AsyncIterator[dict[str, object]]:
        yield self._phase("Recall", "active")
        await self.plugins.run_pre_recall(state)
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Recall"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        yield self._log("info", "Retrieving memory context (DSM + RLD + TraceMemory + MemoryField).")
        yield self._tool_call("memory_recall", status="running", target="All Memory Systems")
        await asyncio.sleep(0.3)

        # ✅ IMPROVED: Get conversation context for better recall (increased from 5 to 10)
        conversation_context = ""
        if self.conversation and len(self.conversation) > 1:
            conversation_context = self.conversation.get_context_string(n=10, include_metadata=True)
            yield self._log("info", f"Loaded conversation context: {len(self.conversation)} messages, using last 10")

        # Get structured memory context with conversation history
        state.memory_context_structured = await self._safe_recall_structured(
            memory, state.task, conversation_context
        )
        state.memory_context = state.memory_context_structured["full_context"]

        # Log memory utilization
        has_memory = state.memory_context_structured.get("has_memory", False)
        similar_count = len(state.memory_context_structured.get("similar_solutions", []))
        rld_count = len(state.memory_context_structured.get("rld_genes", []))
        dsm_count = len(state.memory_context_structured.get("dsm_segments", []))

        state.states.append(state.memory_context)
        state.actions.append(f"Loaded memory: {similar_count} similar solutions, {rld_count} RLD genes, {dsm_count} DSM segments")
        state.tools_used.append("rld")
        state.tools_used.append("dsm")
        state.tools_used.append("trace_memory")
        state.tools_used.append("memory_field")

        await asyncio.sleep(0.2 if self.config.execution.ui_delays_enabled else 0)
        detail = f"{len(state.memory_context)} chars, {similar_count} solutions, {rld_count} genes"
        yield self._tool_call("memory_recall", status="done", target="All Memory Systems", detail=detail)

        if has_memory:
            yield self._log("success", f"Memory loaded: {similar_count} similar solutions, {rld_count} reasoning patterns.")
        else:
            yield self._log("warning", "Cold start: no relevant memory found, bootstrapping from workspace.")

        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Recall"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        await self.plugins.run_post_recall(state)
        yield self._phase("Recall", "done")

    # --- Phase: Reason (patch generation) -----------------------------------
    async def _reason(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
        iteration: int,
    ) -> AsyncIterator[dict[str, object]]:
        import json
        import re
        yield self._phase("Reason", "active")
        await self.plugins.run_pre_reason(state, iteration)
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Reason", iteration),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        yield self._log("info", f"Generating patch with LLM, iteration {iteration}.")

        # --- HIERARCHICAL PLANNING: Generate task plan on first iteration ---
        if iteration == 1 and self.gemini.configured:
            try:
                from planning import HierarchicalPlanner, PlanningContext

                planner = HierarchicalPlanner()
                context = PlanningContext(
                    goal=state.task,
                    workspace_path=state.workspace,
                    available_tools=["file_reader", "file_writer", "terminal", "pytest", "github_list_repos", "github_get_repo_info", "github_list_branches", "github_create_pr", "github_clone_repo"]
                )

                # Generate hierarchical plan
                task_graph = await asyncio.to_thread(planner.plan, state.task, context)
                state.task_graph = task_graph  # ✅ Store for execution

                # Convert to frontend format
                def task_to_dict(task):
                    return {
                        "id": task.id,
                        "title": task.description,
                        "status": "pending",
                        "estimatedTime": f"~{task.estimated_time}min" if task.estimated_time else None,
                        "subtasks": [task_to_dict(st) for st in task.subtasks] if task.subtasks else []
                    }

                plan_data = [task_to_dict(t) for t in task_graph.tasks.values() if not task_graph.get_dependencies(t.id)]

                # Send plan to frontend
                yield {
                    "type": "task_plan",
                    "plan": plan_data
                }

                yield self._log("success", f"Generated execution plan with {len(task_graph.tasks)} tasks")

                # ✅ NEW: Check if task should be decomposed
                # If task is complex (>3 subtasks), execute them sequentially
                root_tasks = [t for t in task_graph.tasks.values() if not task_graph.get_dependencies(t.id)]
                if len(root_tasks) > 1 or (root_tasks and len(root_tasks[0].subtasks) > 2):
                    yield self._log("info", f"Task decomposed into {len(task_graph.tasks)} subtasks. Executing sequentially...")
                    state.actions.append(f"Task decomposed into {len(task_graph.tasks)} subtasks")
            except Exception as e:
                print(f"[AGENT] Planning failed (non-fatal): {e}")

        # --- PRE-READ: Ask LLM which files to read first ---
        file_contents: dict[str, str] = {}
        if iteration == 1 and self.gemini.configured:
            try:
                plan_prompt = (
                    f"TASK: {state.task}\n\n"
                    f"WORKSPACE FILES:\n{state.workspace_summary[:6000]}\n\n"
                    "List the file paths (max 8) that need to be READ to complete this task. "
                    "Return ONLY a JSON array of relative file paths, e.g. [\"src/main.py\", \"lib/utils.ts\"]. "
                    "No markdown, no explanation."
                )
                raw_files = await retry_async(
                    lambda: self.gemini.generate_text(
                        plan_prompt,
                        "You are a code analysis agent. Return only a JSON array of file paths."
                    ),
                    policy=LLM_RETRY_POLICY,
                )
                import json, re
                cleaned = raw_files.strip()
                # Extract JSON array
                match = re.search(r'\[.*\]', cleaned, re.DOTALL)
                if match:
                    paths = json.loads(match.group(0))
                    if isinstance(paths, list):
                        for p in paths[:8]:
                            if isinstance(p, str):
                                yield self._tool_call("read_file", status="running", target=p)
                                content = await asyncio.to_thread(read_file, state.workspace, p)
                                if not content.startswith("ERROR:"):
                                    file_contents[p] = content
                                    line_count = len(content.splitlines())
                                    yield self._tool_call("read_file", status="done", target=p, detail=f"{line_count} lines", result=content)
                                    yield self._tool_activity(
                                        f"Read {line_count} lines",
                                        message=p,
                                        target=p,
                                    )
                                else:
                                    yield self._tool_call("read_file", status="error", target=p, detail="File not found")
                        if file_contents:
                            yield self._log("info", f"Pre-read {len(file_contents)} files.")
                        state.actions.append(f"Pre-read {len(file_contents)} files for context")
                        state.tools_used.append("file-reader")
            except Exception as e:
                print(f"[AGENT] Pre-read failed (non-fatal): {e}")

        # --- Build Failure Guidelines & Health Metrics ---
        failure_guidelines = ""
        if self.failure_history:
            lines = [
                "WARNING: The following attempts to fix the task FAILED. Avoid repeating the same mistakes!",
                "--- FAILED ATTEMPTS HISTORY ---"
            ]
            for record in self.failure_history:
                lines.append(f"Attempt {record.iteration}:")
                lines.append(f"  Changed Files: {', '.join(record.changed_files) if record.changed_files else 'None'}")
                if record.patch_diff:
                    # ✅ OPTIMIZE: Limit diff to 500 chars instead of full diff
                    diff_preview = record.patch_diff[:500]
                    if len(record.patch_diff) > 500:
                        diff_preview += "\n  ... [truncated for brevity]"
                    lines.append("  Patch Diff:\n  " + diff_preview.replace("\n", "\n  "))
                if record.error:
                    # ✅ OPTIMIZE: Limit error to last 300 chars
                    err_preview = record.error[-300:]
                    lines.append("  Error output:\n  " + err_preview.replace("\n", "\n  "))
                lines.append("-" * 30)

            lines.append(
                "CRITICAL DIRECTIVE:\n"
                "Analyze the above errors. Do not generate the exact same patches or run the same failing commands. "
                "Think step-by-step why the previous attempts failed and choose a different, logically sound approach."
            )
            failure_guidelines = "\n".join(lines)

            # ✅ OPTIMIZE: Limit total failure_guidelines to 2000 chars
            if len(failure_guidelines) > 2000:
                failure_guidelines = failure_guidelines[:2000] + "\n... [truncated - see pattern above]"

        previous_err_combined = state.last_error
        if failure_guidelines:
            previous_err_combined = f"{failure_guidelines}\n\nLatest Error:\n{state.last_error}"

        workspace_summary_enriched = (
            f"=== CODEBASE HEALTH METRICS ===\n"
            f"Average Cyclomatic Complexity: {state.complexity_avg}\n"
            f"Circular Dependencies Detected: {state.circular_dependencies}\n"
            f"================================\n\n"
            f"{state.workspace_summary}"
        )

        # ✅ OPTIMIZE: Use short summary if conversation history exists
        if len(self.conversation_history) > 2:
            # Agent already knows workspace - use short summary
            workspace_summary_enriched = (
                f"=== CODEBASE HEALTH (cached) ===\n"
                f"Files: {state.total_files}, Complexity: {state.complexity_avg}\n"
                f"Circular Deps: {state.circular_dependencies}\n"
                f"Note: Full workspace context was provided in previous messages.\n"
                f"================================\n"
            )
            yield self._log("info", "Using short workspace summary (full context in conversation history)")

        # --- Add Semantic Graph and Dependency Analysis to context ---
        semantic_context = ""
        if state.semantic_graph:
            try:
                # ✅ OPTIMIZE: Skip semantic graph if conversation history exists
                if len(self.conversation_history) <= 2:
                    # First request - include full semantic context using new to_prompt_context()
                    semantic_context = state.semantic_graph.to_prompt_context(max_modules=10, max_classes_per_module=5)

                    # Add circular dependencies if detected
                    if state.circular_dependencies > 0:
                        from analysis.code.dependency import DependencyAnalyzer
                        dep_analyzer = DependencyAnalyzer(state.workspace)
                        dep_graph = dep_analyzer.get_graph()
                        circular = dep_graph.get_circular_dependencies()
                        if circular:
                            semantic_context += "\n\n## ⚠️ Circular Dependencies Detected\n"
                            for cycle in circular[:5]:
                                semantic_context += f"  - {' → '.join(cycle)}\n"

                    yield self._log("info", "Added semantic graph and dependency analysis to context.")
                else:
                    # Subsequent requests - skip (already in conversation history)
                    semantic_context = "=== SEMANTIC GRAPH (cached) ===\nFull semantic graph was provided in previous messages.\n"
                    yield self._log("info", "Skipped semantic graph (using cached from conversation history)")
            except Exception as e:
                print(f"[AGENT] Semantic context generation failed (non-fatal): {e}")

        # Enrich memory context with structured data
        memory_context_enriched = state.memory_context
        if state.memory_context_structured.get("has_memory"):
            # ✅ OPTIMIZE: Limit memory context size
            similar_solutions = state.memory_context_structured.get("similar_solutions", [])
            if similar_solutions:
                memory_context_enriched += "\n\n=== RECOMMENDED APPROACH (Based on Similar Past Solutions) ===\n"
                # Limit to top 2 solutions (was unlimited)
                for idx, sol in enumerate(similar_solutions[:2], 1):
                    memory_context_enriched += f"\n[Approach {idx}] (Similarity: {sol['similarity']:.2f})\n"
                    memory_context_enriched += f"Tools to use: {', '.join(sol['tools_used'][:5])}\n"  # Limit tools
                    memory_context_enriched += f"Key steps:\n"
                    # Limit to 3 actions (was unlimited)
                    for action in sol['actions'][:3]:
                        memory_context_enriched += f"  - {action[:100]}\n"  # Truncate long actions

            # Add RLD genes section
            rld_genes = state.memory_context_structured.get("rld_genes", [])
            if rld_genes:
                memory_context_enriched += "\n\n=== REASONING PATTERNS (RLD Genes) ===\n"
                # Limit to top 3 genes (was unlimited)
                for gene in rld_genes[:3]:
                    # gene is a ReasoningGene object, not a dict
                    if hasattr(gene, 'task_context'):
                        success_rate = gene.stats.success_rate if hasattr(gene, 'stats') else 0
                        memory_context_enriched += f"- Pattern: {gene.task_context[:100]} (success rate: {success_rate:.1%})\n"
                        memory_context_enriched += f"  Tools: {', '.join(gene.tools_used[:5])}\n"  # Limit tools
                    else:
                        # Fallback for dict format
                        success_rate = gene.get('success_rate', 0)
                        pattern = gene.get('task_context', gene.get('pattern', 'unknown'))
                        memory_context_enriched += f"- Pattern: {pattern[:100]} (success rate: {success_rate:.1%})\n"
                        tools = gene.get('tools_used', gene.get('tools', []))
                        memory_context_enriched += f"  Tools: {', '.join(tools[:5])}\n"

        # Combine all context
        full_context = workspace_summary_enriched
        if semantic_context:
            full_context += f"\n\n{semantic_context}"
        if memory_context_enriched:
            full_context += f"\n\n{memory_context_enriched}"

        # ✅ ADD CONVERSATION HISTORY TO CONTEXT
        conversation_context = self._format_history()
        if conversation_context:
            full_context = f"{conversation_context}\n\n{full_context}"
            yield self._log("info", f"Added conversation history ({len(self.conversation_history)} messages) to context.")

        # ✅ LOG CONTEXT SIZE
        context_size = len(full_context)
        context_size_kb = context_size / 1024
        yield self._log("info", f"Total context size: {context_size_kb:.1f} KB ({context_size:,} chars)")

        # ✅ PROACTIVE CONTEXT REDUCTION: Limit to 40KB to prevent API errors
        MAX_CONTEXT_SIZE = 40_000  # 40 KB limit (reduced for API stability)
        if context_size > MAX_CONTEXT_SIZE:
            yield self._log("warning", f"Context too large ({context_size_kb:.1f} KB), reducing to {MAX_CONTEXT_SIZE/1024:.1f} KB")

            # Reduce each component proportionally
            reduction_ratio = MAX_CONTEXT_SIZE / context_size

            workspace_summary_enriched = workspace_summary_enriched[:int(len(workspace_summary_enriched) * reduction_ratio)]
            if semantic_context:
                semantic_context = semantic_context[:int(len(semantic_context) * reduction_ratio)]
            if memory_context_enriched:
                memory_context_enriched = memory_context_enriched[:int(len(memory_context_enriched) * reduction_ratio)]

            # Rebuild full_context
            full_context = workspace_summary_enriched
            if semantic_context:
                full_context += f"\n\n{semantic_context}"
            if memory_context_enriched:
                full_context += f"\n\n{memory_context_enriched}"

            if conversation_context:
                full_context = f"{conversation_context}\n\n{full_context}"

            # Truncate if still too large
            if len(full_context) > MAX_CONTEXT_SIZE:
                full_context = full_context[:MAX_CONTEXT_SIZE] + "\n... [truncated to fit context limit]"

            context_size = len(full_context)
            context_size_kb = context_size / 1024
            yield self._log("info", f"Reduced context size: {context_size_kb:.1f} KB ({context_size:,} chars)")

        # --- Generate patch with enriched context ---
        yield self._tool_call("llm_generate", status="running", target=self.gemini.model_id if hasattr(self.gemini, 'model_id') else "LLM", detail=f"iteration {iteration}")
        await asyncio.sleep(0.4 if self.config.execution.ui_delays_enabled else 0)

        # ✅ IMPROVED: Don't pass conversation_context to LLM - conversation_history already contains it
        # This prevents duplication and reduces context size
        # conversation_context is only used for memory recall, not for LLM generation

        # Use regular Gemini client (no Antigravity SDK dependency) with automatic context reduction on timeout/error
        try:
            generated = await retry_async(
                lambda: self.gemini.generate_patch(
                    task=state.task,
                    workspace_summary=full_context,
                    memory_context=memory_context_enriched,
                    previous_error=previous_err_combined,
                    action_history=state.actions,
                    file_contents=file_contents,
                    conversation_history=self.conversation_history,
                    conversation_context=None,  # ✅ FIX: Don't duplicate - already in conversation_history
                ),
                policy=LLM_RETRY_POLICY,
            )
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout) as exc:
            yield self._log("warning", f"Генерация патча завершилась с ошибкой или таймаутом: {exc}. Снижаю размер контекста и пробую снова...")

            # Reduce context dynamically
            ws_summary_reduced = full_context[:6000] + "\n... [truncated due to timeout] ..."
            mem_context_reduced = memory_context_enriched[:4000] + "\n... [truncated due to timeout] ..."
            file_contents_reduced = {}
            for path, content in file_contents.items():
                file_contents_reduced[path] = content[:4000] + "\n... [truncated due to timeout] ..."

            # Retry once with reduced context
            try:
                generated = await retry_async(
                    lambda: self.gemini.generate_patch(
                        task=state.task,
                        workspace_summary=ws_summary_reduced,
                        memory_context=mem_context_reduced,
                        previous_error=previous_err_combined,
                        action_history=state.actions,
                        file_contents=file_contents_reduced,
                        conversation_history=self.conversation_history,
                        conversation_context=None,  # ✅ FIX: Don't duplicate
                    ),
                    policy=LLM_RETRY_POLICY,
                )
            except Exception as retry_exc:
                # If retry also fails, return informational response instead of crashing
                yield self._log("error", f"Вторая попытка также завершилась ошибкой: {retry_exc}. Возвращаю информационный ответ.")
                generated = GeneratedPatch(
                    rationale=f"Не удалось сгенерировать патч из-за таймаута LLM. Задача: {state.task}",
                    subtasks=[],
                    files={},
                    commands=[]
                )
            
        state.last_rationale = generated.rationale
        await self.plugins.run_post_reason(state, generated, iteration)
        await asyncio.sleep(0.2 if self.config.execution.ui_delays_enabled else 0)
        yield self._tool_call("llm_generate", status="done", target="LLM (Antigravity)", detail=f"{len(generated.files)} files, {len(generated.commands)} commands")

        if generated.rationale:
            yield self._thinking(generated.rationale)

        # Task Decomposition
        if generated.subtasks:
            yield self._log("info", "Subtasks:\n" + "\n".join(f" - {t}" for t in generated.subtasks))
            state.actions.append(f"Decomposed task into {len(generated.subtasks)} subtasks")

        # Tool Router: Run Terminal Commands
        command_failed = False
        if generated.commands:
            for command in generated.commands:
                yield self._log("info", f"$ {command}")
                yield self._tool_call("terminal", status="running", target=command)
                await asyncio.sleep(0.3)
                cmd_result = await asyncio.to_thread(run_terminal_command, state.workspace, command)
                state.actions.append(f"Executed: {command} (code {cmd_result.exit_code})")
                state.tools_used.append("terminal")
                await asyncio.sleep(0.2 if self.config.execution.ui_delays_enabled else 0)
                if cmd_result.success:
                    yield self._tool_call("terminal", status="done", target=command, detail=f"exit {cmd_result.exit_code}")
                    yield self._tool_activity("Ran command", message=command, target="terminal")
                    yield self._log("success", f"Command OK:\n{cmd_result.output[-4000:]}")
                else:
                    command_failed = True
                    yield self._tool_call("terminal", status="error", target=command, detail=f"exit {cmd_result.exit_code}")
                    state.last_error = f"Command '{command}' failed with exit code {cmd_result.exit_code}:\n{cmd_result.output[-4000:]}"
                    yield self._log("error", state.last_error)

        # If there are no files to change
        if not generated.files:
            state.states.append(generated.rationale)
            if not generated.commands:
                state.actions.append("Answered without file modifications.")
                state.tools_used.append("gemini-rest")

                try:
                    import os
                    # Read README.md if it exists in the workspace
                    readme_content = ""
                    readme_path = os.path.join(state.workspace, "README.md")
                    if os.path.exists(readme_path):
                        try:
                            with open(readme_path, "r", encoding="utf-8") as rf:
                                readme_content = rf.read(12000)
                        except Exception:
                            pass
                    
                    # Clip AST summary to avoid proxy timeout
                    ws_summary_clipped = state.workspace_summary or ""
                    if len(ws_summary_clipped) > 8000:
                        ws_summary_clipped = ws_summary_clipped[:8000] + "\n... [truncated for brevity] ..."

                    rich_prompt = (
                        f"User request: {state.task}\n\n"
                        f"Workspace README.md:\n{readme_content}\n\n"
                        f"Workspace AST summary (clipped):\n{ws_summary_clipped}\n\n"
                        f"Associative Memory Context (from DSM/RLD):\n{state.memory_context}\n\n"
                        f"Autonomous operating policy:\n{AUTONOMOUS_AGENT_POLICY}\n\n"
                        "Please answer the user's request thoroughly and naturally. "
                        "Since the query is informational/read-only, write a comprehensive, high-quality response. "
                        "Do not include any file-change instructions or patch content in the response. "
                        "Write the response in the same language the user asked in (which is usually Russian)."
                    )
                    rich_response = await retry_async(
                        lambda: self.gemini.generate_text(
                            rich_prompt,
                            inject_persona(
                                f"{AUTONOMOUS_AGENT_POLICY}\n\n"
                                "Provide a professional, friendly, and very detailed response to the user's query about the project or code. "
                                "Structure your reply with clean markdown headers and bullet points. "
                                "Answer in the same language as the user query."
                            )
                        ),
                        policy=LLM_RETRY_POLICY,
                    )
                    state.last_rationale = rich_response
                except Exception as exc:
                    print(f"[AGENT] Rich response generation failed: {exc}")
                    # Use the rationale from the patch response as fallback
                    if generated.rationale and not generated.rationale.startswith("[LLM"):
                        state.last_rationale = generated.rationale
                yield self._log("success", "Answered without code changes.")
            else:
                state.changes_made = True
                yield self._log("success", generated.rationale or "Commands executed.")
            yield self._phase("Reason", "done")
            return

        # Multi-file Reasoning: Apply file edits
        # ✅ SAFETY CHECK: Ensure generated.files is not empty
        if not generated.files:
            yield self._log("warning", "No files to patch, skipping file operations")
            yield self._phase("Reason", "done")
            return

        yield self._log("info", f"Patching {len(generated.files)} file(s)...")
        for path in generated.files:
            yield self._tool_call("write_file", status="running", target=path, args={"path": path, "content": generated.files.get(path, "")})
            await asyncio.sleep(0.15 if self.config.execution.ui_delays_enabled else 0)  # Small delay per file
        # Diff Preview before apply
        proposed_patch_diff = "\n".join([f"--- {p}\n+++ {p}\n{c[:50]}..." for p, c in generated.files.items()])
        yield {
            "type": "diff_preview",
            "files": list(generated.files.keys()),
            "diff": proposed_patch_diff,
            "message": "Awaiting approval for patch..."
        }
        # Emulate waiting for user approval (in a real system, the websocket would pause here)
        yield self._log("info", "Diff preview approved autonomously (Diff Preview mode active).")

        # Convert generated.files dict to list of ProposedFileChange
        changes = [
            ProposedFileChange(path=path, content=content)
            for path, content in generated.files.items()
        ]
        patch = await asyncio.to_thread(apply_changes, state.workspace, changes)
        state.current_changed_files = patch.changed_files
        state.final_diff = patch.diff or await asyncio.to_thread(git_diff, state.workspace)
        state.changes_made = True
        state.states.append(generated.rationale)
        state.actions.append(f"Applied patch touching {len(patch.changed_files)} files")
        state.tools_used.append("gemini-rest")
        state.tools_used.append("file-writer")
        yield self._log("info", f"Applied patch to {len(patch.changed_files)} files.")
        for changed_file in patch.changed_files:
            content = generated.files.get(changed_file, "")
            lines_changed = len(content.splitlines())
            await asyncio.sleep(0.1 if self.config.execution.ui_delays_enabled else 0)
            yield self._tool_call("write_file", status="done", target=changed_file, lines_changed=lines_changed, args={"path": changed_file, "content": content})
            yield self._tool_activity("Updated file", message=changed_file, target=changed_file)
        yield {"type": "diff", "diff": state.final_diff, "files": patch.changed_files}

        if command_failed:
            yield self._log("error", "Patch applied, but some terminal commands failed.")
        else:
            yield self._log("success", generated.rationale or "Patch generated and applied.")
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Reason", iteration),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }

        # ✅ SAVE AGENT RESPONSE TO CONVERSATION HISTORY
        agent_response = generated.rationale or "Code changes applied"
        if generated.files:
            agent_response += f"\n\nModified files: {', '.join(generated.files.keys())}"
        if generated.commands:
            agent_response += f"\n\nExecuted commands: {', '.join(generated.commands)}"

        self.conversation_history.append({"role": "assistant", "content": agent_response})

        # Keep history manageable (last 20 messages)
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

        yield self._phase("Reason", "done")

    # --- Phase: Stabilize (test) --------------------------------------------
    async def _stabilize(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
        iteration: int,
    ) -> AsyncIterator[dict[str, object]]:
        yield self._phase("Stabilize", "active")
        await self.plugins.run_pre_stabilize(state, iteration)
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Stabilize", iteration),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }

        if not state.changes_made:
            yield self._log("info", "No file changes to test.")
            yield self._phase("Stabilize", "done")
            return

        yield self._log("info", "Running tests to validate changes.")
        yield self._tool_call("pytest", status="running", target=str(state.workspace))
        await asyncio.sleep(0.5 if self.config.execution.ui_delays_enabled else 0)

        try:
            test_result = await asyncio.to_thread(run_pytest, state.workspace)
        except subprocess.TimeoutExpired:
            yield self._log("warning", "Tests timed out after 300 seconds. Skipping validation phase.")
            yield self._tool_call("pytest", status="done", target=str(state.workspace), detail="timeout - skipped")
            yield self._phase("Stabilize", "done")
            state.actions.append("Ran pytest: timeout - validation skipped")
            state.tools_used.append("pytest")
            return

        state.actions.append(f"Ran pytest: exit_code={test_result.exit_code}, success={test_result.success}")
        state.tools_used.append("pytest")

        await asyncio.sleep(0.3)
        yield self._tool_call("pytest", status="done", target=str(state.workspace), detail=f"exit_code={test_result.exit_code}")

        # --- SELF-CORRECTION: If tests failed, analyze and retry ---
        if not test_result.success:
            yield self._log("warning", "Tests failed. Analyzing errors...")

            # Use FailureAnalyzer to understand the error
            failure_context = FailureContext(
                iteration=iteration,
                changed_files=state.current_changed_files,
                error_output=test_result.output,
                test_failures=1,  # We don't have exact count, use 1
                workspace_summary=state.workspace_summary[:2000]
            )

            analysis = await asyncio.to_thread(self.failure_analyzer.analyze, failure_context)

            # Build error context for retry
            error_summary = f"""
=== TEST FAILURES DETECTED ===
Exit code: {test_result.exit_code}
Root cause: {analysis.root_cause}

Suggested fix: {analysis.suggested_fix}

Error output:
{test_result.output[-2000:]}

CRITICAL: The previous code changes caused test failures. You MUST fix these errors.
Do NOT repeat the same approach. Analyze why the tests failed and generate a corrected solution.
"""

            state.last_error = error_summary
            yield self._log("error", f"Root cause: {analysis.root_cause}")
            yield self._log("info", f"Suggested fix: {analysis.suggested_fix}")

            # ═══ Feed test results back to conversation_history ═══
            # This is critical: LLM must see what actually happened (like mistral-vibe)
            # so it doesn't "lie" or repeat the same mistake
            test_feedback = (
                f"[TOOL RESULT: pytest]\n"
                f"Status: FAILED (exit code {test_result.exit_code})\n"
                f"Root cause: {analysis.root_cause}\n"
                f"Suggested fix: {analysis.suggested_fix}\n"
                f"Output (last 1000 chars):\n{test_result.output[-1000:]}"
            )
            self.conversation_history.append({"role": "user", "content": test_feedback})
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

            # Record failure for learning
            self.failure_history.append(FailureRecord(
                iteration=iteration,
                changed_files=state.current_changed_files,
                error=test_result.output,
                patch_diff=state.final_diff
            ))

            # Update MemoryField with failure
            await self._safe_memory_field_update(memory, "Reason", "Stabilize", success=False)

            # Check if we should retry (max 3 attempts)
            max_retries = 3
            if iteration < max_retries:
                yield self._log("warning", f"Attempt {iteration}/{max_retries} failed. Retrying with error context...")
                yield {
                    "type": "cognitive_update",
                    "mode": "Self-Correction",
                    "energy_ledger": self._get_energy_ledger(state, memory, "Stabilize", iteration),
                    "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else [],
                    "retry": True,
                    "iteration": iteration,
                    "max_retries": max_retries
                }

                # Return to Phase 3 (Reason) with error context
                # This will be handled by the main loop
                yield self._phase("Stabilize", "retry")
                return
            else:
                yield self._log("error", f"Max retries ({max_retries}) reached. Tests still failing.")
                yield {
                    "type": "cognitive_update",
                    "mode": "Failed",
                    "energy_ledger": self._get_energy_ledger(state, memory, "Stabilize", iteration),
                    "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else [],
                    "max_retries_reached": True
                }
                yield self._phase("Stabilize", "failed")
                return

        # Tests passed - success!
        yield self._log("success", f"All tests passed (exit code {test_result.exit_code}).")

        # ═══ Feed success back to conversation_history ═══
        self.conversation_history.append({
            "role": "user",
            "content": f"[TOOL RESULT: pytest]\nStatus: PASSED (exit code {test_result.exit_code})\nAll changes validated successfully."
        })
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Stabilize", iteration),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }

        # Update MemoryField with success
        await self._safe_memory_field_update(memory, "Reason", "Stabilize", success=True)

        await self.plugins.run_post_stabilize(state, iteration)
        yield self._phase("Stabilize", "done")

    async def _commit(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
    ) -> AsyncIterator[dict[str, object]]:
        yield self._phase("Commit", "active")
        await self.plugins.run_pre_commit(state)
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Commit"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        final_answer = "\n".join(
            [
                "Task completed by Sharrowkin.",
                "Final diff:",
                state.final_diff,
            ]
        )
        yield self._tool_call("memory_store", status="running", target="DSM + RLD")

        # ✅ IMPROVED: Get conversation summary for commit (increased from 3 to 5)
        conversation_summary = ""
        if self.conversation and len(self.conversation) > 0:
            conversation_summary = self.conversation.get_context_string(n=5, include_metadata=True)
            yield self._log("info", f"Saving conversation context to memory: {len(conversation_summary)} chars")

        await self._safe_learn_success(
            memory,
            task=state.task,
            states=state.states,
            actions=state.actions,
            final_answer=final_answer,
            tools_used=state.tools_used,
            changed_files=state.current_changed_files,
            workspace_summary=conversation_summary  # Pass conversation as workspace_summary
        )

        # ✅ NEW: Save assistant response to conversation
        if self.conversation:
            self.conversation.add_message(
                "assistant",
                state.last_rationale or "Task completed successfully",
                metadata={
                    "tools_used": state.tools_used,
                    "files_changed": state.current_changed_files
                }
            )

        # ✅ NEW: Record task completion in learning modules
        task_duration = time.time() - task_start_time if 'task_start_time' in dir() else 0

        if self.strategy_optimizer:
            self.strategy_optimizer.record_task(
                task=state.task,
                tools_used=state.tools_used,
                iterations=len(state.states),
                success=True,
                duration_seconds=task_duration
            )
            yield self._log("info", "Strategy optimizer updated")

        if self.meta_learner:
            self.meta_learner.record_task_completion(
                task=state.task,
                success=True,
                iterations=len(state.states),
                duration=task_duration,
                memory_used=bool(state.memory_context),
                strategy_used=None  # Could be extracted from state
            )
            yield self._log("info", "Meta-learner updated")

        yield self._tool_call("memory_store", status="done", target="DSM + RLD + Learning", detail="Solution committed")
        yield self._log("success", "Solution committed to memory.")
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Commit"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        await self.plugins.run_post_commit(state)
        yield self._phase("Commit", "done")
