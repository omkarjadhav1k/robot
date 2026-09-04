"""Pytest fixtures for backend tests."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.robots import _robot_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear in-memory robot registry before each test to ensure test isolation."""
    _robot_registry.clear()
    yield
    _robot_registry.clear()


@pytest.fixture
def client() -> TestClient:
    """Synchronous test client for FastAPI endpoints."""
    with TestClient(app) as test_client:
        yield test_client
