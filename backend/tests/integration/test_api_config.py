"""Tests for /api/config endpoints."""

from unittest.mock import patch


def test_profile_returns_null_by_default(client):
    """Without TENET_PROFILE, the endpoint returns null."""
    response = client.get("/api/config/profile")
    assert response.status_code == 200
    assert response.json() == {"profile": None}


def test_profile_returns_active_profile(client):
    """With an active profile, the endpoint returns the profile name."""
    with patch("api.config.ACTIVE_PROFILE", "paper"):
        response = client.get("/api/config/profile")
    assert response.status_code == 200
    assert response.json() == {"profile": "paper"}
