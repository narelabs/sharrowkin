"""Phase 4: Stabilize - Patch application and validation.

Handles applying patches, syntax checking, and error recovery.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator
import asyncio

from core.tools import apply_changes, ProposedFileChange


class StabilizeModule:
    """Phase 4: Stabilize - Apply and validate patches."""

    def __init__(self, config: Any):
        self.config = config

    async def stabilize(
        self,
        workspace: Path,
        patch: dict[str, Any],
        ui_delays_enabled: bool = False
    ) -> AsyncIterator[dict[str, Any]]:
        """Apply patch and validate changes.

        Yields:
            Status updates and validation results
        """
        if ui_delays_enabled:
            await asyncio.sleep(0.2)

        files = patch.get("files", [])
        if not files:
            yield {
                "type": "error",
                "error": "No files in patch",
            }
            return

        # Convert to ProposedFileChange format
        changes = []
        for file_data in files:
            change = ProposedFileChange(
                path=file_data.get("path", ""),
                content=file_data.get("content", ""),
                operation=file_data.get("operation", "write"),
            )
            changes.append(change)

        yield {
            "type": "applying_changes",
            "file_count": len(changes),
        }

        # Apply changes
        try:
            result = apply_changes(workspace, changes)

            if result.get("success"):
                yield {
                    "type": "changes_applied",
                    "changed_files": result.get("changed_files", []),
                }

                # Syntax validation
                validation = await self._validate_syntax(workspace, result.get("changed_files", []))

                if validation["valid"]:
                    yield {
                        "type": "validation_success",
                        "message": "All changes validated successfully",
                    }
                else:
                    yield {
                        "type": "validation_error",
                        "error": validation["error"],
                    }

            else:
                yield {
                    "type": "error",
                    "error": result.get("error", "Unknown error applying changes"),
                }

        except Exception as e:
            yield {
                "type": "error",
                "error": str(e),
            }

    async def _validate_syntax(self, workspace: Path, changed_files: list[str]) -> dict[str, Any]:
        """Validate syntax of changed Python files."""
        import ast

        for file_path in changed_files:
            if not file_path.endswith(".py"):
                continue

            full_path = workspace / file_path
            if not full_path.exists():
                continue

            try:
                code = full_path.read_text(encoding="utf-8")
                ast.parse(code)
            except SyntaxError as e:
                return {
                    "valid": False,
                    "error": f"Syntax error in {file_path}:{e.lineno}: {e.msg}",
                }
            except Exception as e:
                return {
                    "valid": False,
                    "error": f"Error validating {file_path}: {str(e)}",
                }

        return {"valid": True}
