"""GitHub integration for Sharrowkin Agent.

Provides OAuth authentication, repository management, PR/Issues operations.
"""

from .oauth import GitHubOAuth
from .api import GitHubAPI
from .repository import GitHubRepository

__all__ = [
    "GitHubOAuth",
    "GitHubAPI",
    "GitHubRepository",
]
