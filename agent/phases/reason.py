"""Phase 3: Reason - LLM-based reasoning and patch generation.

Handles prompt construction, LLM calls, and patch generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator
import asyncio

from core.llm.client import GeminiClient
from agent.failure_analyzer import FailureAnalyzer, FailureContext


class ReasonModule:
    """Phase 3: Reason - Generate solution patches via LLM."""

    def __init__(self, gemini_client: GeminiClient, failure_analyzer: FailureAnalyzer, config: Any):
        self.gemini = gemini_client
        self.failure_analyzer = failure_analyzer
        self.config = config

    async def reason(
        self,
        task: str,
        workspace_summary: str,
        memory_context: str,
        previous_error: str,
        action_history: list[str],
        file_contents: dict[str, str],
        failure_history: list[Any],
        ui_delays_enabled: bool = False
    ) -> AsyncIterator[dict[str, Any]]:
        """Generate patch using LLM reasoning.

        Yields:
            Status updates and final patch result
        """
        if ui_delays_enabled:
            await asyncio.sleep(0.3)

        # Build failure guidelines from history
        failure_guidelines = ""
        if failure_history:
            failure_context = FailureContext(
                task=task,
                workspace_summary=workspace_summary,
                failure_history=failure_history,
            )
            analysis = self.failure_analyzer.analyze(failure_context)
            failure_guidelines = analysis.get("guidelines", "")

            # ✅ Limit to 2000 chars to prevent context explosion
            if len(failure_guidelines) > 2000:
                failure_guidelines = failure_guidelines[:2000] + "\n... [truncated]"

        # Build prompt
        prompt = self._build_prompt(
            task=task,
            workspace_summary=workspace_summary,
            memory_context=memory_context,
            previous_error=previous_error,
            action_history=action_history,
            file_contents=file_contents,
            failure_guidelines=failure_guidelines,
        )

        yield {"type": "reasoning", "message": "Generating patch with LLM..."}

        # Call LLM
        try:
            response = await self.gemini.generate_text(
                prompt=prompt,
                system_instruction="You are Sharrowkin, an autonomous coding agent.",
            )

            # Parse response for patch
            patch = self._parse_patch(response)

            yield {
                "type": "patch_generated",
                "patch": patch,
                "rationale": response[:500],  # First 500 chars as rationale
            }

        except Exception as e:
            yield {
                "type": "error",
                "error": str(e),
            }

    def _build_prompt(
        self,
        task: str,
        workspace_summary: str,
        memory_context: str,
        previous_error: str,
        action_history: list[str],
        file_contents: dict[str, str],
        failure_guidelines: str,
    ) -> str:
        """Build LLM prompt from context."""
        parts = [
            f"# Task\n{task}",
            f"\n# Workspace\n{workspace_summary[:1000]}",  # Limit workspace summary
        ]

        if memory_context:
            parts.append(f"\n# Memory Context\n{memory_context[:1000]}")  # Limit memory

        if previous_error:
            parts.append(f"\n# Previous Error\n{previous_error[:500]}")  # Limit error

        if action_history:
            parts.append(f"\n# Action History\n" + "\n".join(action_history[-5:]))  # Last 5 actions

        if file_contents:
            parts.append("\n# Relevant Files")
            for path, content in list(file_contents.items())[:3]:  # Max 3 files
                parts.append(f"\n## {path}\n```\n{content[:1000]}\n```")  # Limit file content

        if failure_guidelines:
            parts.append(f"\n# Failure Guidelines\n{failure_guidelines}")

        parts.append("\n# Instructions\nGenerate a patch to solve the task. Output format: JSON with 'files' array.")

        return "\n".join(parts)

    def _parse_patch(self, response: str) -> dict[str, Any]:
        """Parse LLM response into patch format."""
        import json
        import re

        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return raw response
        return {
            "files": [],
            "raw_response": response,
        }
