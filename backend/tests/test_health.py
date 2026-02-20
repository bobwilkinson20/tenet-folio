"""Basic health check tests."""


def test_health_check(client):
    """Test that the health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
