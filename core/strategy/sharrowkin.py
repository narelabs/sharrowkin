import asyncio
import os
import uuid
from typing import Any, AsyncIterator
import pydantic

from core import types
from core.hooks.runner import HookRunner
from core.hooks.base import SessionContext, TurnContext
from core.llm.client import GeminiClient, AUTONOMOUS_AGENT_POLICY, GeneratedPatch
from core.tools import run_terminal_command, apply_changes, git_diff, run_pytest, read_file, list_files, ProposedFileChange

class SharrowkinAgentConfig(pydantic.BaseModel):
    """Configuration for Sharrowkin Agent."""
    workspace_path: str = ""
    max_history_size: int = 15
    compaction_threshold: int = 12


class SharrowkinConnection:
    def __init__(self, config: SharrowkinAgentConfig, tool_runner: Any, hook_runner: Any):
        self.config = config
        self.tool_runner = tool_runner
        self.hook_runner = hook_runner
        self._is_idle = True
        self._steps_queue = asyncio.Queue()
        self.client = GeminiClient()
        
        self.workspace = config.workspace_path or os.getcwd()
        self.history_steps: list[types.Step] = []
        self._loop_task = None
        self._turn_context = None
        
        # Pending approvals (event, tool_call, result)
        self.pending_approval = None

    @property
    def is_idle(self) -> bool:
        return self._is_idle

    @property
    def conversation_id(self) -> str:
        return "sharrowkin-session-local"

    async def send(self, prompt: types.Content | None, **kwargs: Any) -> None:
        if not self._is_idle:
            raise RuntimeError("Connection is not idle")
        self._is_idle = False
        
        # Create a new background loop task
        self._loop_task = asyncio.create_task(self._run_loop(prompt))

    async def receive_steps(self) -> AsyncIterator[types.Step]:
        while not self._is_idle or not self._steps_queue.empty():
            try:
                # Wait for the next step with a timeout to avoid hanging if the queue is empty
                step = await asyncio.wait_for(self._steps_queue.get(), timeout=1.0)
                yield step
                self._steps_queue.task_done()
            except asyncio.TimeoutError:
                if self._is_idle and self._steps_queue.empty():
                    break

    async def disconnect(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()

    async def _compact_context(self):
        # Math of compaction: if history exceeds threshold, compact it to max size
        if len(self.history_steps) > self.config.max_history_size:
            # We will merge the middle steps (turns) into a summary step
            # Keeping the first step (which is usually the task prompt) and the last few steps
            to_compact = self.history_steps[1:-3]
            if not to_compact:
                return

            print(f"[COMPACTION] Compacting {len(to_compact)} steps...")
            
            # Request summary from GeminiClient
            summary_prompt = (
                "You are a system context compactor. Summarize the actions, file changes, and command outputs "
                "recorded in the following agent step history into a concise, detailed technical paragraph "
                "describing the current progress and state. Do not include raw terminal output.\n\n"
            )
            for idx, s in enumerate(to_compact):
                summary_prompt += f"Step {idx}: Source={s.source}, Type={s.type}, Content={s.content[:300]}\n"
                if s.tool_calls:
                    summary_prompt += f"  Tools: {', '.join(tc.name for tc in s.tool_calls)}\n"
            
            try:
                summary = await asyncio.to_thread(self.client.generate_text, summary_prompt, "You are a compiler/summarizer.")
            except Exception as e:
                summary = f"Context compacted due to size. (Summary failed: {e})"
                
            # Create a COMPACTION step
            compaction_step = types.Step(
                id=str(uuid.uuid4()),
                step_index=len(self.history_steps),
                type=types.StepType.COMPACTION,
                source=types.StepSource.SYSTEM,
                target=types.StepTarget.USER,
                status=types.StepStatus.DONE,
                content=f"=== CONTEXT COMPACTION SUMMARY ===\n{summary}\n===================================",
            )
            
            # Reconstruct history: Keep element 0, insert compaction, keep last 3 elements
            self.history_steps = [self.history_steps[0], compaction_step] + self.history_steps[-3:]
            
            # Emit compaction step to UI
            await self._steps_queue.put(compaction_step)
            
            # Dispatch compaction hook if registered
            if self.hook_runner:
                await self.hook_runner.dispatch_compaction(self._turn_context, {"compaction": summary})

    def _format_prompt_with_history(self, prompt: types.Content | None) -> str:
        formatted = ""
        for s in self.history_steps:
            role = "User" if s.source == types.StepSource.USER else "Agent"
            if s.type == types.StepType.COMPACTION:
                formatted += f"\n[SYSTEM COMPACTION]: {s.content}\n"
            elif s.content:
                formatted += f"\n{role}: {s.content}\n"
            elif s.thinking:
                formatted += f"\nAgent Rationale: {s.thinking}\n"
        
        # Add the new prompt
        if prompt:
            formatted += f"\nUser: {prompt}\n"
        return formatted

    async def _run_loop(self, prompt: types.Content | None):
        try:
            # 1. Initialize Turn Context
            if self.hook_runner:
                pre_turn_res, self._turn_context = await self.hook_runner.dispatch_pre_turn(str(prompt))
                if not pre_turn_res.allow:
                    err_step = types.Step(
                        id=str(uuid.uuid4()),
                        type=types.StepType.SYSTEM_MESSAGE,
                        source=types.StepSource.SYSTEM,
                        status=types.StepStatus.ERROR,
                        content=f"Turn denied: {pre_turn_res.message}"
                    )
                    await self._steps_queue.put(err_step)
                    return
            else:
                self._turn_context = TurnContext(SessionContext())

            # Append user prompt to history
            if prompt:
                user_step = types.Step(
                    id=str(uuid.uuid4()),
                    step_index=len(self.history_steps),
                    type=types.StepType.TEXT_RESPONSE,
                    source=types.StepSource.USER,
                    target=types.StepTarget.ENVIRONMENT,
                    status=types.StepStatus.DONE,
                    content=str(prompt)
                )
                self.history_steps.append(user_step)
                await self._steps_queue.put(user_step)

            # 2. Context Compaction Check
            await self._compact_context()

            # 3. Cognitive iteration
            success = False
            for iteration in range(1, 4):  # limit self-healing iteration loop
                # Call GeminiClient using our custom prompt formatting
                # Since the agent must be smart, we enrichment the workspace summary
                workspace_summary = ""
                try:
                    from core.tools import scan_workspace, summarize_workspace
                    summaries = await asyncio.to_thread(scan_workspace, self.workspace)
                    workspace_summary = summarize_workspace(summaries)
                except Exception:
                    pass

                llm_prompt = (
                    f"WORKSPACE FILE PATHS:\n{workspace_summary[:4000]}\n\n"
                    f"HISTORY & CURRENT STATE:\n{self._format_prompt_with_history(None)}\n\n"
                    f"TASK/PROMPT:\n{prompt}\n\n"
                    "Analyze the task. Provide a JSON response describing your rationale, and any actions to take (files to write, commands to run)."
                )
                
                # Model call
                step_id = str(uuid.uuid4())
                generating_step = types.Step(
                    id=step_id,
                    step_index=len(self.history_steps),
                    type=types.StepType.TEXT_RESPONSE,
                    source=types.StepSource.MODEL,
                    status=types.StepStatus.ACTIVE,
                    content="Thinking..."
                )
                await self._steps_queue.put(generating_step)
                
                try:
                    from core.llm_client import _autonomous_json_system_prompt
                    raw_response = await asyncio.to_thread(
                        self.client.generate_text,
                        llm_prompt,
                        _autonomous_json_system_prompt()
                    )
                except Exception as e:
                    err_step = types.Step(
                        id=step_id,
                        type=types.StepType.SYSTEM_MESSAGE,
                        source=types.StepSource.SYSTEM,
                        status=types.StepStatus.ERROR,
                        content=f"LLM Call Failed: {e}"
                    )
                    await self._steps_queue.put(err_step)
                    break

                # Clean response
                import json, re
                cleaned = raw_response.strip()
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                
                parsed = None
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                    except Exception:
                        pass
                
                if not parsed:
                    # Model failed to output JSON, treat as text response
                    text_step = types.Step(
                        id=step_id,
                        step_index=len(self.history_steps),
                        type=types.StepType.TEXT_RESPONSE,
                        source=types.StepSource.MODEL,
                        status=types.StepStatus.DONE,
                        content=cleaned
                    )
                    self.history_steps.append(text_step)
                    await self._steps_queue.put(text_step)
                    break

                # Model outputted patch structure
                rationale = parsed.get("rationale", "")
                files = parsed.get("files", {})
                commands = parsed.get("commands", [])
                subtasks = parsed.get("subtasks", [])

                # Update the active step with thinking and rationale
                generating_step.status = types.StepStatus.DONE
                generating_step.thinking = rationale
                generating_step.content = f"Rationale: {rationale}"
                self.history_steps.append(generating_step)
                await self._steps_queue.put(generating_step)

                # Execute File Edits
                files_changed = []
                for path, content in files.items():
                    tool_call = types.ToolCall(
                        id=str(uuid.uuid4()),
                        name="write_file",
                        args={"path": path, "content": content}
                    )
                    
                    # Decide Hook layer
                    hook_allow = True
                    hook_msg = ""
                    if self.hook_runner:
                        res, _, op_ctx = await self.hook_runner.dispatch_pre_tool_call(self._turn_context, tool_call)
                        hook_allow = res.allow
                        hook_msg = res.message
                    
                    if not hook_allow:
                        # Denied by policy
                        tc_step = types.Step(
                            id=str(uuid.uuid4()),
                            step_index=len(self.history_steps),
                            type=types.StepType.TOOL_CALL,
                            source=types.StepSource.MODEL,
                            status=types.StepStatus.ERROR,
                            content=f"File Edit Denied: {hook_msg}",
                            tool_calls=[tool_call]
                        )
                        self.history_steps.append(tc_step)
                        await self._steps_queue.put(tc_step)
                        continue

                    # Apply change
                    changes = [ProposedFileChange(path=path, content=content)]
                    patch = await asyncio.to_thread(apply_changes, self.workspace, changes)
                    files_changed.extend(patch.changed_files)
                    
                    # Yield completion
                    tc_step = types.Step(
                        id=str(uuid.uuid4()),
                        step_index=len(self.history_steps),
                        type=types.StepType.TOOL_CALL,
                        source=types.StepSource.MODEL,
                        status=types.StepStatus.DONE,
                        content=f"Successfully edited: {path}",
                        tool_calls=[tool_call]
                    )
                    self.history_steps.append(tc_step)
                    await self._steps_queue.put(tc_step)

                # Execute Commands
                command_errors = []
                for cmd in commands:
                    tool_call = types.ToolCall(
                        id=str(uuid.uuid4()),
                        name="run_command",
                        args={"CommandLine": cmd}
                    )
                    
                    # Safety Decide Hook
                    hook_allow = True
                    hook_msg = ""
                    if self.hook_runner:
                        res, _, op_ctx = await self.hook_runner.dispatch_pre_tool_call(self._turn_context, tool_call)
                        hook_allow = res.allow
                        hook_msg = res.message

                    if not hook_allow:
                        tc_step = types.Step(
                            id=str(uuid.uuid4()),
                            step_index=len(self.history_steps),
                            type=types.StepType.TOOL_CALL,
                            source=types.StepSource.MODEL,
                            status=types.StepStatus.ERROR,
                            content=f"Command Denied: {hook_msg}",
                            tool_calls=[tool_call]
                        )
                        self.history_steps.append(tc_step)
                        await self._steps_queue.put(tc_step)
                        continue

                    # Run command
                    cmd_step = types.Step(
                        id=str(uuid.uuid4()),
                        step_index=len(self.history_steps),
                        type=types.StepType.TOOL_CALL,
                        source=types.StepSource.MODEL,
                        status=types.StepStatus.ACTIVE,
                        content=f"Running command: {cmd}",
                        tool_calls=[tool_call]
                    )
                    await self._steps_queue.put(cmd_step)

                    cmd_res = await asyncio.to_thread(run_terminal_command, self.workspace, cmd)
                    
                    if cmd_res.success:
                        cmd_step.status = types.StepStatus.DONE
                        cmd_step.content = f"Command output:\n{cmd_res.output[-1500:]}"
                    else:
                        cmd_step.status = types.StepStatus.ERROR
                        cmd_step.content = f"Command failed (exit {cmd_res.exit_code}):\n{cmd_res.output[-1500:]}"
                        command_errors.append(cmd_res.output)
                        
                    self.history_steps.append(cmd_step)
                    await self._steps_queue.put(cmd_step)

                # Execute Tests / Stabilization
                if files_changed or commands:
                    # Run tests if pytest.ini exists or tests directory exists
                    test_needed = os.path.exists(os.path.join(self.workspace, "pytest.ini")) or os.path.isdir(os.path.join(self.workspace, "tests"))
                    if test_needed:
                        test_step = types.Step(
                            id=str(uuid.uuid4()),
                            step_index=len(self.history_steps),
                            type=types.StepType.TOOL_CALL,
                            source=types.StepSource.SYSTEM,
                            status=types.StepStatus.ACTIVE,
                            content="Running tests...",
                            tool_calls=[types.ToolCall(name="run_tests", args={})]
                        )
                        await self._steps_queue.put(test_step)
                        
                        test_res = await asyncio.to_thread(run_pytest, self.workspace)
                        if test_res.success:
                            test_step.status = types.StepStatus.DONE
                            test_step.content = "All tests passed successfully!"
                            success = True
                        else:
                            test_step.status = types.StepStatus.ERROR
                            test_step.content = f"Test failure output:\n{test_res.output[-1500:]}"
                            # Push error to history so LLM can heal next iteration
                            prompt = f"Tests failed. Please review the output and fix it:\n{test_res.output[-1000:]}"
                        
                        self.history_steps.append(test_step)
                        await self._steps_queue.put(test_step)
                        
                        if success:
                            break
                    else:
                        # No tests config, assume ok if no command errors
                        if not command_errors:
                            success = True
                            break
                        else:
                            prompt = f"Previous command failed. Please resolve the issue:\n" + "\n".join(command_errors)
                else:
                    # Informational task completed without changes
                    success = True
                    break

            # 4. Finish step
            finish_step = types.Step(
                id=str(uuid.uuid4()),
                step_index=len(self.history_steps),
                type=types.StepType.FINISH,
                source=types.StepSource.MODEL,
                status=types.StepStatus.DONE if success else types.StepStatus.ERROR,
                content="Task execution completed."
            )
            self.history_steps.append(finish_step)
            await self._steps_queue.put(finish_step)

            # Dispatch post-turn
            if self.hook_runner:
                await self.hook_runner.dispatch_post_turn(self._turn_context, "Task finished.")

        except Exception as e:
            # Catch all errors
            err_step = types.Step(
                id=str(uuid.uuid4()),
                type=types.StepType.SYSTEM_MESSAGE,
                source=types.StepSource.SYSTEM,
                status=types.StepStatus.ERROR,
                content=f"Execution error: {e}"
            )
            await self._steps_queue.put(err_step)
        finally:
            self._is_idle = True
