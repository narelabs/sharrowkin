"""Agent self-awareness system - tracks and reports every action."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime


ActionType = Literal[
    "thinking",
    "tool_call",
    "testing",
    "reading_file",
    "writing_file",
    "running_command",
    "llm_generation",
    "memory_search",
    "planning"
]


@dataclass
class AgentAction:
    """Represents a single agent action with full context."""

    action_type: ActionType
    timestamp: str
    description: str
    target: str | None = None
    status: Literal["started", "running", "done", "error"] = "started"
    details: dict = field(default_factory=dict)

    def to_event(self) -> dict:
        """Convert to WebSocket event format."""
        return {
            "type": "agent_awareness",
            "action": {
                "type": self.action_type,
                "timestamp": self.timestamp,
                "description": self.description,
                "target": self.target,
                "status": self.status,
                "details": self.details
            }
        }


class AwarenessTracker:
    """Tracks all agent actions for self-awareness."""

    def __init__(self):
        self.actions: list[AgentAction] = []
        self.current_phase: str = "idle"
        self.current_iteration: int = 0

    def track_thinking(self, content: str) -> AgentAction:
        """Track thinking/reasoning action."""
        action = AgentAction(
            action_type="thinking",
            timestamp=datetime.now().isoformat(),
            description=f"Reasoning: {content[:100]}...",
            details={"content": content, "phase": self.current_phase}
        )
        self.actions.append(action)
        return action

    def track_tool_call(self, tool_name: str, target: str, status: str = "started") -> AgentAction:
        """Track tool invocation."""
        action = AgentAction(
            action_type="tool_call",
            timestamp=datetime.now().isoformat(),
            description=f"Using tool: {tool_name}",
            target=target,
            status=status,
            details={"tool": tool_name, "iteration": self.current_iteration}
        )
        self.actions.append(action)
        return action

    def track_testing(self, test_type: str, status: str = "started") -> AgentAction:
        """Track testing action."""
        action = AgentAction(
            action_type="testing",
            timestamp=datetime.now().isoformat(),
            description=f"Running tests: {test_type}",
            status=status,
            details={"test_type": test_type, "iteration": self.current_iteration}
        )
        self.actions.append(action)
        return action

    def track_file_read(self, file_path: str) -> AgentAction:
        """Track file reading."""
        action = AgentAction(
            action_type="reading_file",
            timestamp=datetime.now().isoformat(),
            description=f"Reading file: {file_path}",
            target=file_path,
            details={"phase": self.current_phase}
        )
        self.actions.append(action)
        return action

    def track_file_write(self, file_path: str, status: str = "started") -> AgentAction:
        """Track file writing."""
        action = AgentAction(
            action_type="writing_file",
            timestamp=datetime.now().isoformat(),
            description=f"Writing file: {file_path}",
            target=file_path,
            status=status,
            details={"phase": self.current_phase}
        )
        self.actions.append(action)
        return action

    def track_command(self, command: str, status: str = "started") -> AgentAction:
        """Track terminal command execution."""
        action = AgentAction(
            action_type="running_command",
            timestamp=datetime.now().isoformat(),
            description=f"Executing: {command}",
            target=command,
            status=status,
            details={"iteration": self.current_iteration}
        )
        self.actions.append(action)
        return action

    def track_llm_generation(self, model: str, purpose: str, status: str = "started") -> AgentAction:
        """Track LLM generation."""
        action = AgentAction(
            action_type="llm_generation",
            timestamp=datetime.now().isoformat(),
            description=f"LLM generation: {purpose}",
            target=model,
            status=status,
            details={"purpose": purpose, "iteration": self.current_iteration}
        )
        self.actions.append(action)
        return action

    def track_memory_search(self, query: str, results_count: int = 0) -> AgentAction:
        """Track memory search."""
        action = AgentAction(
            action_type="memory_search",
            timestamp=datetime.now().isoformat(),
            description=f"Searching memory: {query[:50]}...",
            status="done",
            details={"query": query, "results": results_count, "phase": self.current_phase}
        )
        self.actions.append(action)
        return action

    def track_planning(self, task_count: int, status: str = "done") -> AgentAction:
        """Track planning action."""
        action = AgentAction(
            action_type="planning",
            timestamp=datetime.now().isoformat(),
            description=f"Generated plan with {task_count} tasks",
            status=status,
            details={"task_count": task_count}
        )
        self.actions.append(action)
        return action

    def update_action_status(self, action: AgentAction, status: str, details: dict | None = None):
        """Update action status."""
        action.status = status
        if details:
            action.details.update(details)

    def set_phase(self, phase: str):
        """Update current phase."""
        self.current_phase = phase

    def set_iteration(self, iteration: int):
        """Update current iteration."""
        self.current_iteration = iteration

    def get_summary(self) -> dict:
        """Get summary of all actions."""
        return {
            "total_actions": len(self.actions),
            "by_type": {
                action_type: len([a for a in self.actions if a.action_type == action_type])
                for action_type in set(a.action_type for a in self.actions)
            },
            "current_phase": self.current_phase,
            "current_iteration": self.current_iteration
        }

    def clear(self):
        """Clear action history."""
        self.actions.clear()
        self.current_phase = "idle"
        self.current_iteration = 0
