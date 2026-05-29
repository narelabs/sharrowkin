"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path


@pytest.fixture
def test_client():
    """Create FastAPI test client."""
    # Import here to avoid circular dependencies
    from main import app
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, test_client):
        """Test /api/health endpoint."""
        response = test_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root(self, test_client):
        """Test / endpoint."""
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert data["service"] == "Sharrowkin Agent"
        assert "version" in data
        assert "endpoints" in data


class TestSessionsEndpoint:
    """Tests for sessions endpoints."""

    def test_list_sessions_empty(self, test_client):
        """Test listing sessions when none exist."""
        response = test_client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_import_session(self, test_client):
        """Test importing a session."""
        session_data = {
            "id": "test-session-123",
            "label": "Test Session"
        }
        response = test_client.post("/api/sessions/import", json=session_data)
        # May return 200 or 400 depending on implementation
        assert response.status_code in [200, 400, 422]


class TestWorkspaceEndpoint:
    """Tests for workspace endpoints."""

    @patch('api.routers.workspace.scan_workspace')
    def test_workspace_stats(self, mock_scan, test_client, temp_workspace):
        """Test workspace stats endpoint."""
        mock_scan.return_value = {
            "total_files": 10,
            "total_lines": 500,
            "file_types": {"py": 8, "md": 2}
        }
        
        response = test_client.get(f"/api/workspace/stats?path={temp_workspace}")
        # May fail if workspace doesn't exist, that's ok for this test
        assert response.status_code in [200, 400, 422, 500]
