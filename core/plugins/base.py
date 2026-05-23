"""Base classes and interfaces for the Sharrowkin plugin architecture.

This module defines the plugin interface, allowing external developers to extend the 
cognitive loop with custom security tools, linters, specialized memory stores, and sandboxing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.core import SharrowkinAgent, AgentRunState
    from core.llm.client import GeneratedPatch


class BasePlugin:
    """Base class for all Sharrowkin plugins.
    
    Subclasses should override the lifecycle methods they want to intercept.
    Hooks can modify the state or perform side effects.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self.enabled = True

    def on_load(self, agent: SharrowkinAgent) -> None:
        """Called when the plugin is registered with the agent."""
        pass

    def on_unload(self, agent: SharrowkinAgent) -> None:
        """Called when the plugin is unregistered."""
        pass

    async def pre_observe(self, state: AgentRunState) -> None:
        """Hook executed before the Observe phase (workspace scanning)."""
        pass

    async def post_observe(self, state: AgentRunState) -> None:
        """Hook executed after workspace scanning completes."""
        pass

    async def pre_recall(self, state: AgentRunState) -> None:
        """Hook executed before memory retrieval."""
        pass

    async def post_recall(self, state: AgentRunState) -> None:
        """Hook executed after memory context is loaded."""
        pass

    async def pre_reason(self, state: AgentRunState, iteration: int) -> None:
        """Hook executed before generating a patch/rationale."""
        pass

    async def post_reason(self, state: AgentRunState, patch: GeneratedPatch, iteration: int) -> None:
        """Hook executed after the LLM generates a patch."""
        pass

    async def pre_stabilize(self, state: AgentRunState, iteration: int) -> None:
        """Hook executed before testing/stabilizing the workspace."""
        pass

    async def post_stabilize(self, state: AgentRunState, success: bool, iteration: int) -> None:
        """Hook executed after running tests."""
        pass

    async def pre_commit(self, state: AgentRunState) -> None:
        """Hook executed before committing the solution to memory."""
        pass

    async def post_commit(self, state: AgentRunState) -> None:
        """Hook executed after commit completes."""
        pass

    async def on_error(self, state: AgentRunState, error: Exception) -> None:
        """Hook executed when any exception occurs during the cognitive loop."""
        pass


class PluginManager:
    """Manages active plugins and handles hook propagation."""

    def __init__(self, agent: SharrowkinAgent) -> None:
        self.agent = agent
        self.plugins: list[BasePlugin] = []

    def register(self, plugin: BasePlugin) -> None:
        """Register and load a plugin."""
        if any(p.name == plugin.name for p in self.plugins):
            return  # Avoid duplicate registration
        plugin.on_load(self.agent)
        self.plugins.append(plugin)

    def unregister(self, plugin_name: str) -> None:
        """Unregister and unload a plugin."""
        for p in self.plugins:
            if p.name == plugin_name:
                p.on_unload(self.agent)
                self.plugins.remove(p)
                break

    async def run_pre_observe(self, state: AgentRunState) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.pre_observe(state)

    async def run_post_observe(self, state: AgentRunState) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.post_observe(state)

    async def run_pre_recall(self, state: AgentRunState) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.pre_recall(state)

    async def run_post_recall(self, state: AgentRunState) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.post_recall(state)

    async def run_pre_reason(self, state: AgentRunState, iteration: int) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.pre_reason(state, iteration)

    async def run_post_reason(self, state: AgentRunState, patch: GeneratedPatch, iteration: int) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.post_reason(state, patch, iteration)

    async def run_pre_stabilize(self, state: AgentRunState, iteration: int) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.pre_stabilize(state, iteration)

    async def run_post_stabilize(self, state: AgentRunState, success: bool, iteration: int) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.post_stabilize(state, success, iteration)

    async def run_pre_commit(self, state: AgentRunState) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.pre_commit(state)

    async def run_post_commit(self, state: AgentRunState) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.post_commit(state)

    async def run_on_error(self, state: AgentRunState, error: Exception) -> None:
        for p in self.plugins:
            if p.enabled:
                await p.on_error(state, error)
