"""Connection strategies for Sharrowkin Agent.

Strategies define how the agent connects and communicates:
- SharrowkinConnection - Main connection strategy with 5-phase cycle
"""

from .sharrowkin import SharrowkinConnection, SharrowkinAgentConfig

__all__ = [
    "SharrowkinConnection",
    "SharrowkinAgentConfig",
]
