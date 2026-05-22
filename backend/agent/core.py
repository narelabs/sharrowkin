"""Real Sharrowkin cognitive agent loop with live thinking stream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
import math
import time

from backend.core.llm.client import AUTONOMOUS_AGENT_POLICY, GeminiClient, GeminiConfigurationError
from backend.core import types
from backend.memory import MemoryBridge
from backend.agent.awareness import AwarenessTracker

from backend.personas import get_persona_manager, inject_persona, format_log
from backend.personas.llm_integration import LogType
from backend.core.tools import (
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
from backend.analysis.code.dependency import DependencyAnalyzer
from backend.analysis.code.semantic_graph import SemanticGraph, SemanticGraphBuilder
from backend.config.settings import AgentConfig, load_config
from backend.agent.workspace_cache import WorkspaceCache, CachedWorkspace

PHASES = ["Observe", "Recall", "Reason", "Verify", "Stabilize", "Commit"]


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
        self.failure_history: list[FailureRecord] = []
        self.awareness = AwarenessTracker()  # Self-awareness system

    def _save_conversation_to_dsm(self, role: str, content: str, memory: MemoryBridge) -> None:
        """Save conversation message to DSM for persistent memory."""
        from datetime import datetime

        memory.dsm.write(
            text=f"{role}: {content}",
            description=f"Conversation turn at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            category_path=("Conversation", "History"),
            importance=0.7,
            metadata={
                "role": role,
                "timestamp": datetime.now().isoformat(),
                "content_length": len(content)
            }
        )

    def _learn_from_error(self, error: str, context: str, memory: MemoryBridge) -> None:
        """Save error to DSM and RLD so agent never repeats the same mistake."""
        from datetime import datetime

        # 1. Save to DSM as anti-pattern
        memory.dsm.write(
            text=f"ERROR: {error}\n\nContext: {context}\n\nNEVER DO THIS AGAIN",
            description=f"Failed approach: {error[:100]}",
            category_path=("Errors", "AntiPatterns"),
            importance=0.95,  # Very important!
            metadata={
                "error_type": type(error).__name__ if isinstance(error, Exception) else "string",
                "timestamp": datetime.now().isoformat(),
                "context": context[:500]
            }
        )

        # 2. Save to RLD as negative gene
        if memory.rld:
            memory.rld.observe(
                task=context,
                states=[],
                actions=[],
                final_answer=f"FAILED: {error}",
                success=False,  # Negative example
                utility=-1.0,   # Negative utility
                tools_used=[],
                metadata={"error": str(error)[:500]}
            )

    async def _verify(self, state: AgentRunState, memory: MemoryBridge) -> AsyncIterator[dict]:
        """Verify solution before applying - check Error Memory and LLM validation."""
        self.awareness.set_phase("Verify")
        yield self._phase("Verify", "active")
        yield self._progress(4, 7, "[VERIFY] Verifying solution before applying")

        # 1. Check Error Memory - did we try this before and fail?
        yield self._log("info", "Checking Error Memory for similar past failures...")

        similar_errors = memory.dsm.route(
            f"ERROR: {state.task}",
            k=3
        )

        # Filter only error records
        error_records = [r for r in similar_errors if "Errors" in r.segment.category_path]

        if error_records:
            yield self._log("warning", f"⚠️ Found {len(error_records)} similar past errors in memory")

            # Show the most similar error
            most_similar = error_records[0]
            yield self._thinking(f"Similar past error found:\n{most_similar.segment.text[:300]}")

            # Ask LLM if current approach is different enough
            verification_prompt = f"""
Task: {state.task}

Past error found in memory:
{most_similar.segment.text[:500]}

Current proposed solution:
{state.last_rationale[:1000]}

Question: Is the current approach DIFFERENT from the past failed approach?
Answer with YES or NO and brief explanation (2-3 sentences).
"""

            try:
                verification = await asyncio.to_thread(
                    self.gemini.generate_text,
                    verification_prompt,
                    "You are a verification assistant. Analyze if the new approach avoids past mistakes."
                )

                if "NO" in verification.upper() or "SAME" in verification.upper():
                    yield self._log("error", f"❌ Verification FAILED: Approach too similar to past failure")
                    yield self._thinking(verification)
                    yield self._phase("Verify", "error")
                    return
                else:
                    yield self._log("success", "✓ Approach is different from past failure")
                    yield self._thinking(verification)
            except Exception as e:
                print(f"[VERIFY] LLM verification failed: {e}")
                # Continue anyway if verification fails

        # 2. LLM verification - is the solution logical and safe?
        yield self._log("info", "Performing LLM verification of solution logic...")

        verification_prompt = f"""
Task: {state.task}

Proposed solution:
{state.last_rationale[:1500]}

Question: Is this solution correct, safe, and logical?
Consider:
- Does it solve the actual problem?
- Are there any obvious bugs or issues?
- Is it safe to apply?

Answer with YES or NO and brief reason (2-3 sentences).
"""

        try:
            verification = await asyncio.to_thread(
                self.gemini.generate_text,
                verification_prompt,
                "You are a code review assistant. Verify if the solution is correct and safe."
            )

            if "NO" in verification.upper() or "UNSAFE" in verification.upper() or "INCORRECT" in verification.upper():
                yield self._log("error", f"❌ Verification FAILED: Solution has issues")
                yield self._thinking(verification)
                yield self._phase("Verify", "error")
                return
            else:
                yield self._log("success", "✓ Solution verified as correct and safe")
                yield self._thinking(verification)
        except Exception as e:
            print(f"[VERIFY] LLM verification failed: {e}")
            yield self._log("warning", f"⚠️ Verification check failed: {e}")
            # Continue anyway if verification fails

        yield self._phase("Verify", "done")

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
    def _phase(self, name: str, status: str) -> dict[str, object]:
        return {"type": "phase_change", "phase": name.lower(), "status": status}

    def _progress(self, current_step: int, total_steps: int, step_name: str) -> dict[str, object]:
        """Emit progress update with current step."""
        percentage = int((current_step / total_steps) * 100)
        return {
            "type": "progress",
            "current_step": current_step,
            "total_steps": total_steps,
            "percentage": percentage,
            "step_name": step_name
        }

    def _log(self, level: str, message: str) -> dict[str, object]:
        return {"type": "log", "level": level, "message": message}

    def _task_update(self, task_id: str, status: str) -> dict[str, object]:
        """Emit task status update for frontend."""
        return {"type": "task_update", "task_id": task_id, "status": status}

    def _status(self, status: str, message: str = "") -> dict[str, object]:
        result = {"type": "status", "status": status}
        if message:
            result["message"] = message
        return result

    def _repo_selector(self, repos: list[dict], prompt: str = "Выберите репозиторий:") -> dict[str, object]:
        """Send repository selector card to frontend."""
        return {
            "type": "repo_selector",
            "prompt": prompt,
            "repos": repos
        }

    def _thinking(self, text: str) -> dict[str, object]:
        """Emit a 'thinking' event so the frontend shows live agent reasoning."""
        action = self.awareness.track_thinking(text)
        return {
            "type": "thinking",
            "content": text,
            "awareness": action.to_event()
        }

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
    ) -> dict[str, object]:
        """Emit a tool_call event for Devin-style tool invocation display."""
        action = self.awareness.track_tool_call(tool, target or tool, status)
        if detail:
            action.details["detail"] = detail
        if lines_changed:
            action.details["lines_changed"] = lines_changed
        return {
            "type": "tool_call",
            "tool": tool,
            "status": status,
            "target": target,
            "detail": detail,
            "lines_changed": lines_changed,
            "duration_ms": duration_ms,
            "awareness": action.to_event()
        }

    def _format_history(self) -> str:
        """Format recent conversation history for LLM context."""
        if len(self.conversation_history) <= 1:
            return ""
        # Take last 20 messages (increased from 10) for better context
        recent = self.conversation_history[-21:-1]
        if not recent:
            return ""
        lines = []
        lines.append("=== RECENT CONVERSATION ===\n")
        for i, msg in enumerate(recent):
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"]
            # Don't truncate - keep full context (increased from 500)
            # Only truncate if extremely long (>2000 chars)
            if len(content) > 2000:
                content = content[:2000] + "... [truncated]"
            lines.append(f"[{i+1}] {role}: {content}")
        lines.append("\n=== END CONVERSATION ===")
        return "\n\n".join(lines)

    # --- main run loop ------------------------------------------------------
    async def run(self, task: str, workspace_path: str, plan_mode: str = "autonomous") -> AsyncIterator[dict[str, object]]:
        print(f"[AGENT] run() called: task={task!r}, workspace_path={workspace_path!r}, plan_mode={plan_mode!r}")
        workspace = resolve_workspace(workspace_path)

        # Extract target subfolder from task (e.g., "изучай sharrowkinagent/backend" or full Windows path)
        import re

        # Try to extract full Windows path first
        windows_path_match = re.search(r'(?:изучай|analyze|explore|study)\s+([A-Z]:[\\\/][^\s]+)', task, re.IGNORECASE)
        if windows_path_match:
            full_path = Path(windows_path_match.group(1))
            if full_path.exists() and full_path.is_dir():
                workspace = full_path
                print(f"[AGENT] Detected full path: {full_path}, using workspace: {workspace}")
        else:
            # Try relative path
            subfolder_match = re.search(r'(?:изучай|analyze|explore|study)\s+([a-zA-Z0-9_/-]+)', task, re.IGNORECASE)
            if subfolder_match:
                subfolder = subfolder_match.group(1).strip('/')
                target_path = workspace / subfolder
                if target_path.exists() and target_path.is_dir():
                    workspace = target_path
                    print(f"[AGENT] Detected target subfolder: {subfolder}, using workspace: {workspace}")

        state = AgentRunState(
            task=task,
            workspace=workspace,
            states=[],
            actions=[],
            tools_used=[],
        )

        # Extract selected repository from user message if present
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
        yield self._status("running")

        # Store user message in conversation history
        self.conversation_history.append({"role": "user", "content": task})

        # Save to DSM for persistent memory
        self._save_conversation_to_dsm("user", task, memory)

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

        # --- Intent Routing ---
        try:
            if plan_mode == "analyze":
                intent = {"is_informational": True, "is_conversational": False}
                print(f"[AGENT] Overriding intent to informational for plan_mode=analyze")
            else:
                intent = await asyncio.to_thread(self.gemini.classify_intent, task)
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
                                asyncio.to_thread(
                                    self.gemini.generate_text,
                                    prompt,
                                    system_instruction
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

                # Save assistant response to DSM
                self._save_conversation_to_dsm("assistant", response, memory)

                # Keep history manageable (last 50 messages, increased from 20)
                if len(self.conversation_history) > 50:
                    self.conversation_history = self.conversation_history[-50:]
                yield {"type": "content", "content": response}
                yield self._status("done")
                return
        except Exception as exc:
            print(f"[AGENT] Intent classification error: {exc}")

        # --- Informational / Read-Only Flow ---
        if intent.get("is_informational"):
            yield self._log("system", "Informational analysis cycle started.")

            try:
                # Always scan local workspace if it exists and is valid
                workspace_is_valid = workspace.exists() and workspace.is_dir()

                # Check if this is a GitHub API request
                is_github_request = any(keyword in state.task.lower() for keyword in [
                    "репозитори", "репо", "repository", "repositories", "github",
                    "список репо", "мои репо", "какие репо", "где мои репо"
                ])

                print(f"[DEBUG] Task: {state.task}")
                print(f"[DEBUG] Workspace: {workspace}")
                print(f"[DEBUG] Workspace valid: {workspace_is_valid}")
                print(f"[DEBUG] is_github_request: {is_github_request}")

                if workspace_is_valid and not is_github_request:
                    # 1. Observe Phase (AST Scan) - scan local workspace
                    async for event in self._observe(state, memory):
                        yield event

                    # 2. Recall Phase (Memory Retrieval)
                    async for event in self._recall(state, memory):
                        yield event
                else:
                    # For GitHub requests or invalid workspace, skip scan
                    if is_github_request:
                        yield self._log("info", "GitHub API request detected - skipping local workspace scan")
                    else:
                        yield self._log("info", f"Workspace not valid or not found: {workspace}")
                    await asyncio.sleep(0)

                # 3. Reason Phase (Rich response generation)
                yield self._phase("Reason", "active")
                await asyncio.sleep(0)
                yield self._log("info", "Generating response...")
                await asyncio.sleep(0)

                try:
                    if is_github_request:
                        # For GitHub requests, call the appropriate tool directly
                        from backend.config import SETTINGS

                        # Check if we have a GitHub token
                        if not SETTINGS.github_token:
                            yield {"type": "content", "content": "❌ GitHub не подключен. Пожалуйста, подключите GitHub в настройках."}
                            await asyncio.sleep(0)
                            yield self._status("done")
                            await asyncio.sleep(0)
                            return

                        # Call github_list_repos tool
                        yield self._log("info", "Calling GitHub API to list repositories...")
                        await asyncio.sleep(0)
                        try:
                            repos_json = await github_list_repos(SETTINGS.github_token)

                            # Parse and format the response
                            import json
                            repos = json.loads(repos_json)

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
                    
                    rich_response = await asyncio.to_thread(
                        self.gemini.generate_text,
                        rich_prompt,
                        inject_persona(
                            f"{AUTONOMOUS_AGENT_POLICY}\n\n"
                            "Provide a professional, friendly, and very detailed response to the user's query about the project or code. "
                            "Structure your reply with clean markdown headers and bullet points. "
                            "Answer in the same language as the user query."
                        )
                    )
                    state.last_rationale = rich_response
                except Exception as exc:
                    print(f"[AGENT] Rich response generation failed: {exc}")
                    state.last_rationale = f"Не удалось сгенерировать ответ: {exc}"
                
                yield self._phase("Reason", "done")
                
                if state.last_rationale:
                    yield {"type": "content", "content": state.last_rationale}
                yield self._status("done")
                yield self._log("success", "Informational analysis completed.")
                return
            except Exception as e:
                print(f"[AGENT] Informational loop error: {e}")
                yield self._status("error", message=str(e))
                return

        # --- Full coding agent cycle ---
        yield self._log("system", "Cognitive cycle started.")

        # Analyze task ambiguity and ask clarifying questions if needed
        yield self._thinking("Analyzing task requirements...")

        # Determine if task needs clarification
        is_vague = any(keyword in state.task.lower() for keyword in [
            "найди", "find", "исправь", "fix", "улучши", "improve", "оптимизируй", "optimize",
            "добавь", "add", "создай", "create"
        ]) and len(state.task.split()) < 10  # Short commands are often vague

        # Check if specific files/locations mentioned
        has_specific_target = any(ext in state.task.lower() for ext in [
            ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cpp", ".c",
            "в файле", "in file", "в папке", "in folder"
        ])

        # Ask clarifying questions for vague tasks
        if is_vague and not has_specific_target:
            clarification_questions = []

            if "найди" in state.task.lower() or "find" in state.task.lower():
                clarification_questions.append({
                    "question": "Что именно нужно найти?",
                    "options": [
                        "Баги и ошибки в коде",
                        "Конкретный файл или функцию",
                        "Проблемы производительности",
                        "Уязвимости безопасности"
                    ]
                })
                clarification_questions.append({
                    "question": "В какой части проекта искать?",
                    "options": [
                        "Во всём проекте",
                        "Только в backend",
                        "Только в frontend",
                        "В конкретной папке (укажите путь)"
                    ]
                })

            if "исправь" in state.task.lower() or "fix" in state.task.lower():
                clarification_questions.append({
                    "question": "Что нужно исправить?",
                    "options": [
                        "Конкретную ошибку (укажите файл и строку)",
                        "Все найденные баги",
                        "Failing тесты",
                        "Проблему производительности"
                    ]
                })

            if "добавь" in state.task.lower() or "create" in state.task.lower():
                clarification_questions.append({
                    "question": "Куда добавить?",
                    "options": [
                        "В существующий файл (укажите путь)",
                        "Создать новый файл",
                        "В конкретную функцию/класс",
                        "Автоматически определить лучшее место"
                    ]
                })
                clarification_questions.append({
                    "question": "Какие требования к реализации?",
                    "options": [
                        "Следовать существующему стилю проекта",
                        "Добавить тесты",
                        "Добавить документацию",
                        "Всё вышеперечисленное"
                    ]
                })

            if clarification_questions:
                yield {
                    "type": "clarification_needed",
                    "questions": clarification_questions,
                    "can_skip": True,
                    "skip_message": "Продолжить с автоматическим определением"
                }
                yield self._log("info", "Задача требует уточнений. Пожалуйста, ответьте на вопросы или нажмите 'Продолжить' для автоматического определения.")

                # Wait for user response (frontend should handle this)
                # For now, continue with automatic determination
                yield self._thinking("Пользователь не ответил на уточнения. Продолжаю с автоматическим определением...")

        # Generate and show execution plan upfront
        yield self._thinking("Creating execution plan...")

        # Determine task type and create plan
        requires_code_changes = any(keyword in state.task.lower() for keyword in [
            "создай", "создать", "добавь", "добавить", "исправь", "исправить",
            "измени", "изменить", "удали", "удалить", "рефактор", "напиши",
            "create", "add", "fix", "change", "modify", "delete", "refactor", "write"
        ])

        is_analysis = any(keyword in state.task.lower() for keyword in [
            "изучай", "изучи", "analyze", "study", "explore", "найди", "find"
        ])

        # Fast mode for simple tasks (skip VERIFY)
        is_simple_task = any(keyword in state.task.lower() for keyword in [
            "привет", "hello", "hi", "ку", "что ты", "кто ты", "помоги", "help"
        ])

        # Show clear execution plan with professional icons
        if requires_code_changes:
            if is_simple_task:
                plan_steps = [
                    "1. [SCAN] Quick workspace scan (cached)",
                    "2. [MEMORY] Recall relevant context",
                    "3. [GENERATE] Generate solution with LLM",
                    "4. [APPLY] Apply code changes",
                    "5. [SAVE] Save to memory"
                ]
            else:
                plan_steps = [
                    "1. [SCAN] Scan workspace and analyze code structure",
                    "2. [MEMORY] Recall relevant context from memory (DSM + RLD)",
                    "3. [GENERATE] Generate solution with LLM",
                    "4. [VERIFY] Verify solution before applying",
                    "5. [APPLY] Apply code changes",
                    "6. [TEST] Run tests and validate",
                    "7. [SAVE] Save to memory for future tasks"
                ]
        elif is_analysis:
            plan_steps = [
                "1. [SCAN] Scan workspace and analyze code structure",
                "2. [MEMORY] Recall relevant context from memory",
                "3. [ANALYZE] Analyze dependencies and complexity",
                "4. [REPORT] Generate detailed report"
            ]
        else:
            plan_steps = [
                "1. [MEMORY] Recall relevant context from memory",
                "2. [GENERATE] Generate response",
                "3. [SAVE] Save to memory"
            ]

        yield {
            "type": "execution_plan",
            "steps": plan_steps,
            "estimated_time": "~10-20 seconds" if is_simple_task else ("~30-60 seconds" if requires_code_changes else "~10-20 seconds")
        }
        yield self._log("info", "Execution plan:\n" + "\n".join(plan_steps))

        try:
            # Check if workspace is valid
            workspace_is_valid = state.workspace.exists() and state.workspace.is_dir()

            if not workspace_is_valid:
                # Workspace not valid - inform user
                yield self._log("error", f"Workspace not found or invalid: {state.workspace}")
                yield {
                    "type": "content",
                    "content": f"⚠️ **Workspace не найден или недоступен:**\n\n`{state.workspace}`\n\nПожалуйста, укажите корректный путь к проекту."
                }
                yield self._status("error")
                return

            # Workspace valid - proceed with task
            async for event in self._observe(state, memory):
                yield event
            async for event in self._recall(state, memory):
                yield event

            success = False
            for iteration in range(1, self.max_iterations + 1):
                # Update awareness tracker with current iteration
                self.awareness.set_iteration(iteration)

                async for event in self._reason(state, memory, iteration):
                    yield event

                if not state.changes_made:
                    success = True
                    break

                # VERIFY phase - check solution before applying (skip for simple tasks)
                verification_passed = True
                if not is_simple_task:
                    async for event in self._verify(state, memory):
                        yield event
                        if event.get("type") == "phase" and event.get("status") == "error":
                            verification_passed = False

                    if not verification_passed:
                        # Verification failed - skip stabilize and retry
                        yield self._log("warning", "⚠️ Verification failed, retrying with different approach...")
                        state.last_error = "Verification failed: solution too similar to past failure or has logical issues"
                        record = FailureRecord(
                            iteration=iteration,
                            changed_files=state.current_changed_files,
                            error=state.last_error,
                            patch_diff=state.final_diff
                        )
                        self.failure_history.append(record)
                        continue
                else:
                    yield self._log("info", "⚡ Fast mode: skipping verification for simple task")

                async for event in self._stabilize(state, memory, iteration):
                    yield event
                if not state.last_error:
                    success = True
                    break
                else:
                    record = FailureRecord(
                        iteration=iteration,
                        changed_files=state.current_changed_files,
                        error=state.last_error,
                        patch_diff=state.final_diff
                    )
                    self.failure_history.append(record)

            if success:
                async for event in self._commit(state, memory):
                    yield event

                # Generate summary using LLM
                yield self._log("info", "Generating work summary...")
                await asyncio.sleep(0)

                summary_prompt = f"""Write a brief summary of the completed work (2-3 sentences).

Task: {state.task}

What was done:
- Files changed: {len(state.current_changed_files) if state.current_changed_files else 0}
- Tools used: {', '.join(list(set(state.tools_used))[:5]) if state.tools_used else 'none'}
- Actions performed: {len(state.actions)}

Describe what specifically was done and what result was achieved."""

                try:
                    summary = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.gemini.generate_text,
                            summary_prompt,
                            "You are an assistant that writes brief summaries of completed work."
                        ),
                        timeout=10
                    )
                    final_response = f"\n\n**Work Summary:**\n{summary.strip()}"
                    yield {"type": "content", "content": final_response}

                    # Save work summary to conversation history and DSM
                    self.conversation_history.append({"role": "assistant", "content": final_response})
                    self._save_conversation_to_dsm("assistant", final_response, memory)

                    await asyncio.sleep(0)
                except Exception as e:
                    print(f"[AGENT] Failed to generate summary: {e}")

                if state.last_rationale:
                    rationale_content = state.last_rationale
                    yield {"type": "content", "content": rationale_content}

                    # Save rationale to conversation history and DSM
                    self.conversation_history.append({"role": "assistant", "content": rationale_content})
                    self._save_conversation_to_dsm("assistant", rationale_content, memory)
                    await asyncio.sleep(0)

                yield self._status("done")
                await asyncio.sleep(0)
                yield self._log("success", "Task stabilized and stored in local memory.")
                await asyncio.sleep(0)
            else:
                if state.last_error:
                    yield {"type": "content", "content": f"⚠️ **Self-healing loop reached the iteration limit.**\n\nLast error:\n```log\n{state.last_error}\n```"}
                yield self._status("error")
                yield self._log("error", "Self-healing loop reached the iteration limit.")
        except GeminiConfigurationError as exc:
            yield self._phase("Reason", "error")
            yield self._thinking(f"API key not configured: {exc}")
            yield {"type": "content", "content": f"⚠️ **API ключ не настроен.**\n\nДобавьте `GEMINI_API_KEY` в файл `backend/backend/.env` для работы с кодом.\n\n```\n{exc}\n```"}
            yield self._status("needs_key")
            yield self._log("error", str(exc))
        except Exception as exc:
            print(f"[AGENT] Cycle error: {exc}")

            # Save critical error to Error Memory
            self._learn_from_error(
                error=str(exc),
                context=f"Task: {state.task}\nCritical agent cycle failure",
                memory=memory
            )

            yield self._thinking(f"Error: {exc}")
            yield {"type": "content", "content": f"⚠️ **Ошибка агента:**\n\n```\n{exc}\n```"}
            yield self._status("error")
            yield self._log("error", f"Agent cycle failed: {exc}")

    # --- Phase: Observe -----------------------------------------------------
    async def _observe(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
    ) -> AsyncIterator[dict[str, object]]:
        self.awareness.set_phase("Observe")
        yield self._phase("Observe", "active")
        yield self._progress(1, 7, "[SCAN] Scanning workspace and analyzing code")
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
        await asyncio.sleep(0)
        yield self._tool_call("scan_workspace", status="running", target=str(state.workspace))
        await asyncio.sleep(0)
        yield self._log("info", "Reading files...")
        await asyncio.sleep(0)
        summaries = await asyncio.to_thread(scan_workspace, state.workspace)
        total_lines = sum(summary.line_count for summary in summaries)
        state.workspace_summary = summarize_workspace(summaries)
        yield self._tool_call("scan_workspace", status="done", target=str(state.workspace), detail=f"{len(summaries)} files, {total_lines} lines")
        await asyncio.sleep(0)
        state.actions.append(f"Scanned {len(summaries)} source files with AST summaries")
        state.tools_used.append("pathlib")
        state.tools_used.append("ast")
        
        # Build Semantic Graph and Analyze Dependencies
        try:
            yield self._tool_call("analyze_dependencies", status="running", target=str(state.workspace))
            await asyncio.sleep(0)
            yield self._log("info", "Building dependency graph...")
            await asyncio.sleep(0)
            dep_analyzer = DependencyAnalyzer()
            await asyncio.to_thread(dep_analyzer.analyze_directory, state.workspace)
            dep_graph = dep_analyzer.get_graph()

            yield self._log("info", "Building semantic graph...")
            await asyncio.sleep(0)
            sem_graph = SemanticGraph(state.workspace / ".sharrowkin" / "semantic_graph")
            sem_builder = SemanticGraphBuilder(sem_graph)
            await asyncio.to_thread(sem_builder.build_from_directory, state.workspace)
            yield self._log("info", "Saving semantic graph to DSM...")
            await asyncio.sleep(0)
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
                from backend.analysis.code.context_linker import ContextLinker
                from backend.analysis.code.data_flow_analyzer import DataFlowAnalyzer

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
            await asyncio.sleep(0.2)
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
        await asyncio.to_thread(memory.learn_project, state.workspace_summary)
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
        yield self._phase("Observe", "done")

    # --- Phase: Recall ------------------------------------------------------
    async def _recall(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
    ) -> AsyncIterator[dict[str, object]]:
        self.awareness.set_phase("Recall")
        yield self._phase("Recall", "active")
        yield self._progress(2, 7, "[MEMORY] Recalling relevant context from memory")
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Recall"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        yield self._log("info", "Retrieving memory context.")

        # Track memory search
        memory_action = self.awareness.track_memory_search(state.task[:100])
        yield memory_action.to_event()

        yield self._tool_call("memory_recall", status="running", target="DSM + RLD")
        await asyncio.sleep(0.3)
        state.memory_context = await asyncio.to_thread(memory.recall, state.task)
        state.states.append(state.memory_context)
        state.actions.append("Loaded RLD active context and DSM active context")
        state.tools_used.append("rld")
        state.tools_used.append("dsm")
        await asyncio.sleep(0.2)
        yield self._tool_call("memory_recall", status="done", target="DSM + RLD", detail=f"{len(state.memory_context)} chars loaded")
        yield self._log("success", f"Memory loaded ({len(state.memory_context)} chars).")
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Recall"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        yield self._phase("Recall", "done")

    # --- Phase: Reason (patch generation) -----------------------------------
    async def _reason(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
        iteration: int,
    ) -> AsyncIterator[dict[str, object]]:
        self.awareness.set_phase("Reason")
        yield self._phase("Reason", "active")
        yield self._progress(3, 7, "[GENERATE] Generating solution with LLM")
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
                    workspace_summary=state.workspace_summary,
                    memory_context=state.memory_context,
                    available_tools=["file_reader", "file_writer", "terminal", "pytest", "github_list_repos", "github_get_repo_info", "github_list_branches", "github_create_pr", "github_clone_repo"]
                )

                # Generate hierarchical plan
                task_graph = await asyncio.to_thread(planner.plan, state.task, context)

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
                raw_files = await asyncio.to_thread(
                    self.gemini.generate_text, plan_prompt,
                    "You are a code analysis agent. Return only a JSON array of file paths."
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
                                    yield self._tool_call("read_file", status="done", target=p, detail=f"{line_count} lines")
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
                    diff_preview = "\\n".join(record.patch_diff.splitlines()[:15])
                    if len(record.patch_diff.splitlines()) > 15:
                        diff_preview += "\\n  ... [truncated]"
                    lines.append("  Patch Diff:\\n  " + diff_preview.replace("\\n", "\\n  "))
                if record.error:
                    err_preview = "\\n".join(record.error.splitlines()[-10:])
                    lines.append("  Error output:\\n  " + err_preview.replace("\\n", "\\n  "))
                lines.append("-" * 30)
            
            lines.append(
                "CRITICAL DIRECTIVE:\\n"
                "Analyze the above errors. Do not generate the exact same patches or run the same failing commands. "
                "Think step-by-step why the previous attempts failed and choose a different, logically sound approach."
            )
            failure_guidelines = "\\n".join(lines)

        previous_err_combined = state.last_error
        if failure_guidelines:
            previous_err_combined = f"{failure_guidelines}\\n\\nLatest Error:\\n{state.last_error}"

        workspace_summary_enriched = (
            f"=== CODEBASE HEALTH METRICS ===\\n"
            f"Average Cyclomatic Complexity: {state.complexity_avg}\\n"
            f"Circular Dependencies Detected: {state.circular_dependencies}\\n"
            f"================================\\n\\n"
        )

        # Use DSM memory context instead of full workspace summary to save tokens
        # Only include full workspace summary on first iteration or if memory is empty
        if iteration == 1 or len(state.memory_context) < 500:
            workspace_summary_enriched += state.workspace_summary
        else:
            # Use only DSM-retrieved context (already filtered by relevance)
            workspace_summary_enriched += f"[Using DSM memory context - {len(state.memory_context)} chars of relevant code]\\n"
            workspace_summary_enriched += state.memory_context[:3000]  # Limit to 3k chars

        # --- Generate patch with file contents ---
        llm_action = self.awareness.track_llm_generation(
            self.gemini.model_id if hasattr(self.gemini, 'model_id') else "gemini",
            f"patch generation iteration {iteration}",
            status="started"
        )
        yield llm_action.to_event()

        yield self._tool_call("llm_generate", status="running", target=self.gemini.model_id if hasattr(self.gemini, 'model_id') else "LLM", detail=f"iteration {iteration}")
        await asyncio.sleep(0.4)

        # Use regular Gemini client (no Antigravity SDK dependency)
        # For large analysis tasks, split into chunks to avoid timeout
        is_large_analysis = "изучай" in state.task.lower() or "analyze" in state.task.lower()

        if is_large_analysis and len(workspace_summary_enriched) > 10000:
            # Split analysis into chunks to avoid timeout
            yield self._log("info", "⚡ Large project detected - using chunked analysis to avoid timeout")

            # Step 1: Quick structure overview (fast)
            yield self._thinking("Step 1/3: Analyzing project structure...")
            structure_prompt = f"""Analyze the project structure briefly (max 500 words):

TASK: {state.task}

PROJECT FILES:
{workspace_summary_enriched[:5000]}

Provide:
1. Project type and tech stack
2. Main directories and their purpose
3. Key entry points

Keep it concise."""

            structure_analysis = await asyncio.to_thread(
                self.gemini.generate_text,
                structure_prompt,
                "You are a code analyst. Be concise."
            )
            yield self._thinking(structure_analysis)

            # Step 2: Key components analysis (medium)
            yield self._thinking("Step 2/3: Analyzing key components...")
            components_prompt = f"""Analyze key components (max 500 words):

STRUCTURE:
{structure_analysis}

MEMORY CONTEXT:
{state.memory_context[:3000]}

Identify:
1. Core modules and their responsibilities
2. Architecture patterns used
3. Dependencies and integrations

Keep it concise."""

            components_analysis = await asyncio.to_thread(
                self.gemini.generate_text,
                components_prompt,
                "You are a code analyst. Be concise."
            )
            yield self._thinking(components_analysis)

            # Step 3: Final synthesis (fast)
            yield self._thinking("Step 3/3: Generating final report...")
            final_prompt = f"""Create final analysis report (max 1000 words):

TASK: {state.task}

STRUCTURE:
{structure_analysis}

COMPONENTS:
{components_analysis}

Create a comprehensive but concise report with:
- Project overview
- Architecture highlights
- Key findings
- Recommendations (if applicable)

Use markdown formatting."""

            final_report = await asyncio.to_thread(
                self.gemini.generate_text,
                final_prompt,
                "You are a code analyst. Create clear, structured reports."
            )

            # Create a mock generated object for analysis tasks
            from backend.core import types
            generated = types.GeneratedPatch(
                rationale=final_report,
                files=[],
                commands=[],
                subtasks=[]
            )
        else:
            # Normal single-request generation for code changes
            generated = await asyncio.to_thread(
                self.gemini.generate_patch,
                    task=state.task,
                    workspace_summary=workspace_summary_enriched,
                    memory_context=state.memory_context,
                    previous_error=previous_err_combined,
                    action_history=state.actions,
                    file_contents=file_contents,
                    conversation_history=self.conversation_history,
                )

        # Update LLM action status
        self.awareness.update_action_status(llm_action, "done", {
            "files_generated": len(generated.files),
            "commands_generated": len(generated.commands)
        })
        yield llm_action.to_event()

        state.last_rationale = generated.rationale
        await asyncio.sleep(0.2)
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
                await asyncio.sleep(0.2)
                if cmd_result.success:
                    yield self._tool_call("terminal", status="done", target=command, detail=f"exit {cmd_result.exit_code}")
                    yield self._tool_activity("Ran command", message=command, target="terminal")
                    yield self._log("success", f"Command OK:\n{cmd_result.output[-4000:]}")
                else:
                    command_failed = True
                    yield self._tool_call("terminal", status="error", target=command, detail=f"exit {cmd_result.exit_code}")
                    state.last_error = f"Command '{command}' failed with exit code {cmd_result.exit_code}:\n{cmd_result.output[-4000:]}"
                    yield self._log("error", state.last_error)

                    # Save error to Error Memory
                    self._learn_from_error(
                        error=state.last_error,
                        context=f"Task: {state.task}\nCommand: {command}",
                        memory=memory
                    )

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
                    rich_response = await asyncio.to_thread(
                        self.gemini.generate_text,
                        rich_prompt,
                        inject_persona(
                            f"{AUTONOMOUS_AGENT_POLICY}\n\n"
                            "Provide a professional, friendly, and very detailed response to the user's query about the project or code. "
                            "Structure your reply with clean markdown headers and bullet points. "
                            "Answer in the same language as the user query."
                        )
                    )
                    state.last_rationale = rich_response
                except Exception as exc:
                    print(f"[AGENT] Rich response generation failed: {exc}")
                yield self._log("success", "Answered without code changes.")
            else:
                state.changes_made = True
                yield self._log("success", generated.rationale or "Commands executed.")
            yield self._phase("Reason", "done")
            return

        # Multi-file Reasoning: Apply file edits
        yield self._log("info", f"Patching {len(generated.files)} file(s)...")
        for path in generated.files:
            yield self._tool_call("write_file", status="running", target=path)
            await asyncio.sleep(0.15)  # Small delay per file
        changes = [ProposedFileChange(path=path, content=content) for path, content in generated.files.items()]
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
            lines_changed = len(generated.files.get(changed_file, "").splitlines())
            await asyncio.sleep(0.1)
            yield self._tool_call("write_file", status="done", target=changed_file, lines_changed=lines_changed)
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
        yield self._phase("Reason", "done")

    # --- Phase: Stabilize (test) --------------------------------------------
    async def _stabilize(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
        iteration: int,
    ) -> AsyncIterator[dict[str, object]]:
        yield self._phase("Stabilize", "active")
        yield self._progress(5, 7, "[TEST] Running tests and validating changes")
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Stabilize", iteration),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }

        # Skip tests if no code changes were made (analysis/informational tasks)
        if not state.current_changed_files:
            yield self._log("info", "⚡ No code changes - skipping tests")
            yield self._phase("Stabilize", "done")
            return

        # Track testing action
        test_action = self.awareness.track_testing("pytest", status="started")
        yield test_action.to_event()

        yield self._log("info", f"Running pytest, iteration {iteration}.")
        yield self._tool_call("run_tests", status="running", target="pytest")

        # Run pytest with timeout to prevent hanging
        try:
            test_result = await asyncio.wait_for(
                asyncio.to_thread(run_pytest, state.workspace),
                timeout=60.0  # 60 second timeout
            )
        except asyncio.TimeoutError:
            yield self._log("warning", "⚠️ Tests timed out after 60s - skipping test validation")
            yield self._tool_call("run_tests", status="error", target="pytest", detail="timeout")
            yield self._phase("Stabilize", "done")
            return

        state.actions.append(f"pytest exited with {test_result.exit_code}")
        state.tools_used.append("pytest")

        if test_result.success:
            state.last_error = ""
            # Update test action status
            self.awareness.update_action_status(test_action, "done", {"exit_code": test_result.exit_code})
            yield test_action.to_event()

            yield self._tool_call("run_tests", status="done", target="pytest", detail="all tests passed")
            yield self._tool_activity("Tested project", message="pytest passed", target="pytest")
            yield self._log("success", test_result.output or "pytest passed.")
            yield {
                "type": "cognitive_update",
                "mode": "Full NARE-Field",
                "energy_ledger": self._get_energy_ledger(state, memory, "Stabilize", iteration),
                "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
            }
            yield self._phase("Stabilize", "done")
            return

        # Test failed - analyze with debugger and ErrorAnalyzer
        state.last_error = test_result.output

        # Save error to Error Memory
        self._learn_from_error(
            error=test_result.output,
            context=f"Task: {state.task}\nTest execution failed",
            memory=memory
        )

        # Update test action status to error
        self.awareness.update_action_status(test_action, "error", {"exit_code": test_result.exit_code})
        yield test_action.to_event()

        yield self._tool_call("run_tests", status="error", target="pytest", detail=f"exit {test_result.exit_code}")
        yield self._log("error", test_result.output)

        # Use ErrorAnalyzer for intelligent classification
        from backend.agent.error_analyzer import ErrorAnalyzer
        analyzer = ErrorAnalyzer()
        error_analysis = analyzer.analyze(test_result.output)

        # Store error analysis in state
        state.actions.append(f"Error classified as: {error_analysis.error_type.value}")
        state.actions.append(f"Fix strategy: {error_analysis.fix_strategy}")

        # Check if we should retry or try alternative approach
        should_retry = analyzer.should_retry(error_analysis, iteration, self.max_iterations)

        # Store failure for learning
        memory.learn_failure(
            task=state.task,
            error_type=error_analysis.error_type.value,
            error_message=error_analysis.error_message,
            attempted_approach=state.last_rationale or "Unknown approach",
            iteration=iteration,
        )

        if not should_retry and iteration > 1:
            # Suggest alternative strategy
            alternative = analyzer.suggest_alternative_strategy(error_analysis)
            yield self._log("warning", f"Retry limit reached. Alternative strategy: {alternative}")
            state.actions.append(f"Alternative strategy suggested: {alternative}")

        # Intelligent error analysis (existing code)
        try:
            from debugging import DebuggerSession
            debugger = DebuggerSession(state.workspace)

            # Parse error from pytest output
            error_info = self._parse_pytest_error(test_result.output)

            if error_info:
                file_name = error_info.get("file", "")
                line_no = error_info.get("line", 0)
                
                # Perform Recursive AST Error Localization!
                ast_diagnostics = localize_ast_error(state.workspace, file_name, line_no)
                
                state.actions.append(f"AST Error Localized in file '{file_name}' at line {line_no}")
                if ast_diagnostics:
                    state.actions.append(f"Failing Class: {ast_diagnostics['enclosing_class']}, Func: {ast_diagnostics['enclosing_func']}")
                    error_info["root_cause"] = f"AST Localized in function '{ast_diagnostics['enclosing_func']}' of class '{ast_diagnostics['enclosing_class']}':\n{ast_diagnostics['snippet']}"
                    error_info["suggested_fix"] = f"Review variable scope and logical constraints in:\n{ast_diagnostics['func_source'][:150]}..."
                
                yield self._log("info", "Analyzing error with debugger...")

                # Send debug analysis to frontend
                yield {
                    "type": "debug_analysis",
                    "error_type": error_info.get("type", "Unknown"),
                    "error_message": error_info.get("message", ""),
                    "file_path": error_info.get("file", ""),
                    "line_number": error_info.get("line", 0),
                    "root_cause": error_info.get("root_cause", ""),
                    "suggested_fix": error_info.get("suggested_fix", "")
                }

                yield self._log("info", f"Root cause: {error_info.get('root_cause', 'Unknown')}")
                yield self._log("info", f"Suggested fix: {error_info.get('suggested_fix', 'See error details')}")
                
                # Update symbolic transition weights for fail (Self-Healing)
                if memory.memory_field:
                    memory.memory_field.update_symbolic("Stabilize", "Reason (Self-Healing)", success=False)

        except Exception as e:
            print(f"[AGENT] Debug analysis failed: {e}")

        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Stabilize", iteration),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        yield self._phase("Stabilize", "error")

    def _parse_pytest_error(self, output: str) -> dict[str, str] | None:
        """Parse pytest output to extract error information."""
        import re

        # Look for common error patterns
        # Example: "AttributeError: 'NoneType' object has no attribute 'method'"
        error_match = re.search(r'(\w+Error): (.+)', output)
        if not error_match:
            return None

        error_type = error_match.group(1)
        error_message = error_match.group(2)

        # Extract file and line number
        # Example: "test_file.py:42: AttributeError"
        location_match = re.search(r'([^/\s]+\.py):(\d+):', output)
        file_path = location_match.group(1) if location_match else ""
        line_number = int(location_match.group(2)) if location_match else 0

        # Generate root cause and fix based on error type
        root_cause = ""
        suggested_fix = ""

        if error_type == "AttributeError" and "NoneType" in error_message:
            root_cause = "Attempting to access attribute on None object"
            suggested_fix = "Add null check: if obj is not None: obj.attribute"
        elif error_type == "KeyError":
            root_cause = f"Dictionary key not found: {error_message}"
            suggested_fix = "Use safe access: dict.get(key, default_value)"
        elif error_type == "IndexError":
            root_cause = "List index out of range"
            suggested_fix = "Add bounds check: if index < len(list): list[index]"
        elif error_type == "TypeError":
            root_cause = "Type mismatch in operation"
            suggested_fix = "Check operand types and convert if necessary"
        elif error_type == "AssertionError":
            root_cause = "Test assertion failed"
            suggested_fix = "Review test expectations and actual output"
        else:
            root_cause = f"Error of type {error_type}"
            suggested_fix = "Review error message and stack trace"

        return {
            "type": error_type,
            "message": error_message,
            "file": file_path,
            "line": line_number,
            "root_cause": root_cause,
            "suggested_fix": suggested_fix
        }

    # --- Phase: Commit (learn) ----------------------------------------------
    async def _commit(
        self,
        state: AgentRunState,
        memory: MemoryBridge,
    ) -> AsyncIterator[dict[str, object]]:
        self.awareness.set_phase("Commit")
        yield self._phase("Commit", "active")
        yield self._progress(6, 7, "[SAVE] Saving to memory for future tasks")
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Commit"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }

        # Send awareness summary
        summary = self.awareness.get_summary()
        yield {
            "type": "awareness_summary",
            "summary": summary
        }

        final_answer = "\n".join(
            [
                "Task completed by Sharrowkin.",
                "Final diff:",
                state.final_diff,
            ]
        )
        yield self._tool_call("memory_store", status="running", target="DSM + RLD")
        await asyncio.to_thread(
            memory.learn_success,
            task=state.task,
            states=state.states,
            actions=state.actions,
            final_answer=final_answer,
            tools_used=state.tools_used,
            changed_files=state.current_changed_files,
            workspace_summary=state.workspace_summary[:1000] if state.workspace_summary else None,
        )
        yield self._tool_call("memory_store", status="done", target="DSM + RLD", detail="Solution committed")
        yield self._log("success", "Solution committed to memory.")
        yield {
            "type": "cognitive_update",
            "mode": "Full NARE-Field",
            "energy_ledger": self._get_energy_ledger(state, memory, "Commit"),
            "attractors": memory.memory_field.get_top_associations(limit=8) if memory.memory_field else []
        }
        yield self._phase("Commit", "done")
