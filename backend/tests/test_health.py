"""Basic health check tests."""

from unittest.mock import patch


def test_health_check(client):
    """Test that the health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_includes_profile(client):
    """When a profile is active, health response includes it."""
    with patch("main.ACTIVE_PROFILE", "paper"):
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["profile"] == "paper"
