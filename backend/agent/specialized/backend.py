"""Backend specialized agent for API/Database development."""

from __future__ import annotations
from pathlib import Path
from typing import AsyncIterator
import asyncio

from ..coordinator import SpecializedAgent, AgentRole, AgentTask


class BackendAgent(SpecializedAgent):
    """Specialized agent for backend development.

    Expertise:
    - REST/GraphQL APIs
    - Database schemas and migrations
    - Authentication/Authorization
    - Business logic
    - Performance optimization
    """

    def __init__(self, workspace: Path, llm_client=None):
        super().__init__(AgentRole.BACKEND, workspace)
        self.llm_client = llm_client

    async def process_task(self, task: AgentTask) -> str:
        """Process backend-related task.

        Args:
            task: Task to process

        Returns:
            Result description
        """
        # Analyze task requirements
        requirements = self._analyze_requirements(task.description)

        # Generate API endpoints
        endpoints = await self._generate_endpoints(requirements)

        # Update database schema if needed
        if requirements.get("needs_database"):
            await self._update_database_schema(requirements)

        # Add authentication if needed
        if requirements.get("needs_auth"):
            await self._add_authentication(requirements)

        return f"Backend implementation complete: {len(endpoints)} endpoints created"

    def _analyze_requirements(self, description: str) -> dict:
        """Analyze task description to extract requirements."""
        desc_lower = description.lower()

        return {
            "needs_database": any(word in desc_lower for word in ["database", "model", "schema", "table"]),
            "needs_auth": any(word in desc_lower for word in ["auth", "login", "user", "permission"]),
            "needs_crud": any(word in desc_lower for word in ["create", "read", "update", "delete", "crud"]),
            "framework": self._detect_framework(),
        }

    def _detect_framework(self) -> str:
        """Detect which backend framework is used."""
        # Check for common files
        if (self.workspace / "requirements.txt").exists():
            try:
                with open(self.workspace / "requirements.txt") as f:
                    content = f.read().lower()
                    if "fastapi" in content:
                        return "fastapi"
                    elif "flask" in content:
                        return "flask"
                    elif "django" in content:
                        return "django"
            except:
                pass

        if (self.workspace / "package.json").exists():
            import json
            try:
                with open(self.workspace / "package.json") as f:
                    data = json.load(f)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                    if "express" in deps:
                        return "express"
                    elif "nestjs" in deps or "@nestjs/core" in deps:
                        return "nestjs"
            except:
                pass

        return "fastapi"  # Default

    async def _generate_endpoints(self, requirements: dict) -> list[str]:
        """Generate API endpoint files based on requirements."""
        endpoints = []

        if requirements["needs_crud"]:
            endpoints.extend(["GET /items", "POST /items", "PUT /items/{id}", "DELETE /items/{id}"])

        if requirements["needs_auth"]:
            endpoints.extend(["POST /auth/login", "POST /auth/register", "POST /auth/logout"])

        # In real implementation, this would:
        # 1. Use LLM to generate actual endpoint code
        # 2. Write files to workspace
        # 3. Update routers/controllers

        return endpoints

    async def _update_database_schema(self, requirements: dict):
        """Update database schema and create migrations."""
        # In real implementation, this would:
        # 1. Detect ORM (SQLAlchemy, Prisma, TypeORM, etc.)
        # 2. Generate model/schema files
        # 3. Create migration files
        # 4. Update database
        pass

    async def _add_authentication(self, requirements: dict):
        """Add authentication middleware and endpoints."""
        # In real implementation, this would:
        # 1. Generate JWT/session handling
        # 2. Add auth middleware
        # 3. Create user model
        # 4. Add password hashing
        pass

    async def stream_progress(self, task: AgentTask) -> AsyncIterator[dict]:
        """Stream progress updates while processing task."""
        yield {"phase": "analyzing", "message": "Analyzing backend requirements"}
        await asyncio.sleep(0.1)

        yield {"phase": "generating", "message": "Generating API endpoints"}
        await asyncio.sleep(0.1)

        yield {"phase": "database", "message": "Updating database schema"}
        await asyncio.sleep(0.1)

        yield {"phase": "complete", "message": "Backend task complete"}
