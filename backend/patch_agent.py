import sys
import re
from pathlib import Path

agent_path = Path("core/agent.py")
code = agent_path.read_text(encoding="utf-8")

# Add the import at the top
if "from google.antigravity" not in code:
    code = code.replace("from memory import MemoryBridge", 
"""from memory import MemoryBridge
try:
    from google.antigravity import Agent as SDKAgent, LocalAgentConfig, CapabilitiesConfig
    HAVE_ANTIGRAVITY = True
except ImportError:
    HAVE_ANTIGRAVITY = False
""")

# We want to intercept the LLM generation block in _reason
# Here is the existing block:
old_block = """        # --- Generate patch with file contents ---
        yield self._tool_call("llm_generate", status="running", target=self.gemini.model_id if hasattr(self.gemini, 'model_id') else "LLM", detail=f"iteration {iteration}")
        await asyncio.sleep(0.4)  # Longer delay for LLM generation to show thinking
        generated = await asyncio.to_thread(
            self.gemini.generate_patch,
            task=state.task,
            workspace_summary=workspace_summary_enriched,
            memory_context=state.memory_context,
            previous_error=previous_err_combined,
            action_history=state.actions,
            file_contents=file_contents,
        )
        state.last_rationale = generated.rationale
        await asyncio.sleep(0.2)
        yield self._tool_call("llm_generate", status="done", target="LLM", detail=f"{len(generated.files)} files, {len(generated.commands)} commands")

        # Show LLM's actual reasoning as thinking
        if generated.rationale:
            yield self._thinking(generated.rationale)"""

new_block = """        # --- Generate patch with file contents ---
        yield self._tool_call("llm_generate", status="running", target=self.gemini.model_id if hasattr(self.gemini, 'model_id') else "LLM", detail=f"iteration {iteration}")
        await asyncio.sleep(0.4)
        
        if HAVE_ANTIGRAVITY:
            config = LocalAgentConfig(
                system_instructions=AUTONOMOUS_AGENT_POLICY,
                capabilities=CapabilitiesConfig()
            )
            # To preserve beautiful UI, we run the agent and intercept streams
            async with SDKAgent(config) as sdk_agent:
                prompt = self.gemini._build_prompt(
                    task=state.task,
                    workspace_summary=workspace_summary_enriched,
                    memory_context=state.memory_context,
                    previous_error=previous_err_combined,
                    action_history=state.actions,
                    file_contents=file_contents,
                ) if hasattr(self.gemini, '_build_prompt') else state.task
                
                # Start chat
                response = await sdk_agent.chat(prompt)
                
                # Since the SDK executes tools natively, we will wait for it to finish and get text
                # In a real app we would `async for t in response.thoughts: yield self._thinking(t)`
                final_text = await response.text()
                
                # We mock a 'GeneratedPatch' so the rest of the flow (_stabilize, _commit) doesn't break
                # Instead of applying changes manually, Antigravity SDK did them!
                # We can skip the manual application by returning an empty files list, but we still want
                # the UI to show success.
                from core.llm_client import GeneratedPatch
                generated = GeneratedPatch(
                    rationale=final_text,
                    subtasks=[],
                    files={},
                    commands=[]
                )
                
                # Did it change anything?
                patch_diff = await asyncio.to_thread(git_diff, state.workspace)
                if patch_diff and len(patch_diff) > 10:
                    state.final_diff = patch_diff
                    state.changes_made = True
                    state.current_changed_files = ["Modifications via Antigravity SDK"]
        else:
            generated = await asyncio.to_thread(
                self.gemini.generate_patch,
                task=state.task,
                workspace_summary=workspace_summary_enriched,
                memory_context=state.memory_context,
                previous_error=previous_err_combined,
                action_history=state.actions,
                file_contents=file_contents,
            )
            
        state.last_rationale = generated.rationale
        await asyncio.sleep(0.2)
        yield self._tool_call("llm_generate", status="done", target="LLM (Antigravity)", detail=f"{len(generated.files)} files, {len(generated.commands)} commands")

        if generated.rationale:
            yield self._thinking(generated.rationale)"""

code = code.replace(old_block, new_block)
agent_path.write_text(code, encoding="utf-8")
print("Agent successfully patched!")
