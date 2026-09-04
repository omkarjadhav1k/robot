"""Unit and integration tests for /health endpoints."""

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Test that root /health endpoint returns 200 and valid JSON schema."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "Business AI Robot"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data
    assert "environment" in data
    assert "database" in data


def test_health_versioned_endpoint(client: TestClient):
    """Test that /api/v1/health returns the exact same health status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_root_discovery_endpoint(client: TestClient):
    """Test that root / endpoint returns service discovery links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Business AI Robot"
    assert data["status"] == "online"
    assert data["docs"] == "/docs"
    assert data["health"] == "/health"
