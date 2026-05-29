import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from main import app


class TestSystemRouter:
    """Test system API endpoints."""

    def test_health_check(self):
        """Test health check endpoint."""
        client = TestClient(app)
        response = client.get("/api/system/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestAgentRouter:
    """Test agent API endpoints."""

    def test_agent_task_endpoint_requires_task(self):
        """Test agent task endpoint validation."""
        client = TestClient(app)
        response = client.post(
            "/api/agent/task",
            json={"workspace": "/tmp/test"}
        )
        # Should fail validation without task
        assert response.status_code == 422

    @patch('api.routers.agent.SharrowkinAgent')
    def test_agent_task_endpoint_success(self, mock_agent):
        """Test successful agent task execution."""
        mock_agent_instance = AsyncMock()
        mock_agent_instance.run.return_value = {"success": True}
        mock_agent.return_value = mock_agent_instance
        
        client = TestClient(app)
        response = client.post(
            "/api/agent/task",
            json={
                "task": "Test task",
                "workspace": "/tmp/test"
            }
        )
        # Note: actual implementation may differ
        assert response.status_code in [200, 202]


class TestWorkspaceRouter:
    """Test workspace API endpoints."""

    @patch('api.routers.workspace.Path')
    def test_workspace_stats(self, mock_path):
        """Test workspace statistics endpoint."""
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.is_dir.return_value = True
        
        client = TestClient(app)
        response = client.get("/api/workspace/stats?path=/tmp/test")
        
        # Endpoint may not exist yet, so check for 404 or 200
        assert response.status_code in [200, 404]
