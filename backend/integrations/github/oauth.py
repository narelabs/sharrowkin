"""GitHub OAuth authentication flow.

Handles OAuth 2.0 authorization code flow for GitHub Apps.
"""

from __future__ import annotations

import os
import secrets
import urllib.parse
from typing import Any

import httpx


class GitHubOAuth:
    """GitHub OAuth 2.0 authentication handler."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ):
        """Initialize GitHub OAuth handler.

        Args:
            client_id: GitHub OAuth App client ID (from env if not provided)
            client_secret: GitHub OAuth App client secret (from env if not provided)
            redirect_uri: OAuth callback URL (from env if not provided)
        """
        self.client_id = client_id or os.getenv("GITHUB_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("GITHUB_CLIENT_SECRET", "")
        self.redirect_uri = redirect_uri or os.getenv(
            "GITHUB_REDIRECT_URI", "http://localhost:3000/api/github/callback"
        )
        self.authorize_url = "https://github.com/login/oauth/authorize"
        self.token_url = "https://github.com/login/oauth/access_token"
        self.api_base = "https://api.github.com"

    @property
    def is_configured(self) -> bool:
        """Check if OAuth credentials are configured."""
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, scopes: list[str] | None = None) -> tuple[str, str]:
        """Generate GitHub OAuth authorization URL.

        Args:
            scopes: List of OAuth scopes to request (default: repo, user, read:org)

        Returns:
            Tuple of (authorization_url, state) where state is CSRF token
        """
        if not self.is_configured:
            raise ValueError("GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.")

        state = secrets.token_urlsafe(32)
        scopes = scopes or ["repo", "user", "read:org", "workflow"]

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "allow_signup": "true",
        }

        url = f"{self.authorize_url}?{urllib.parse.urlencode(params)}"
        return url, state

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Dict with access_token, token_type, scope

        Raises:
            httpx.HTTPError: If token exchange fails
        """
        if not self.is_configured:
            raise ValueError("GitHub OAuth not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                raise ValueError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")

            return data

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get authenticated user information.

        Args:
            access_token: GitHub access token

        Returns:
            Dict with user info (login, id, name, email, avatar_url, etc.)
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json()

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh access token (if GitHub App supports it).

        Note: GitHub OAuth Apps don't support refresh tokens by default.
        GitHub Apps with user-to-server tokens do support refresh.

        Args:
            refresh_token: Refresh token

        Returns:
            Dict with new access_token and refresh_token
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()

    async def revoke_token(self, access_token: str) -> bool:
        """Revoke access token.

        Args:
            access_token: Token to revoke

        Returns:
            True if revoked successfully
        """
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.api_base}/applications/{self.client_id}/token",
                auth=(self.client_id, self.client_secret),
                json={"access_token": access_token},
            )
            return response.status_code == 204
