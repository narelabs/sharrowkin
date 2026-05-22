"""Specialized agents for multi-agent collaboration."""

from .frontend import FrontendAgent
from .backend import BackendAgent
from .qa import QAAgent

__all__ = ["FrontendAgent", "BackendAgent", "QAAgent"]
