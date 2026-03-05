"""Integration tests for the provider setup API endpoints."""

from unittest.mock import patch


class TestGetSetupInfo:
    """Tests for GET /api/providers/{name}/setup-info."""

    def test_returns_simplefin_fields(self, client):
        """Returns field definitions for SimpleFIN."""
        response = client.get("/api/providers/SimpleFIN/setup-info")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["key"] == "setup_token"
        assert data[0]["label"] == "Setup Token"
        assert data[0]["input_type"] == "password"

    def test_returns_plaid_fields(self, client):
        """Returns field definitions for Plaid with select type."""
        response = client.get("/api/providers/Plaid/setup-info")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 3
        assert data[0]["key"] == "client_id"
        assert data[1]["key"] == "secret"
        assert data[2]["key"] == "environment"
        assert data[2]["input_type"] == "select"
        assert len(data[2]["options"]) == 2
        assert data[2]["options"][0]["value"] == "sandbox"

    def test_unknown_provider_404(self, client):
        """Unknown provider returns 404."""
        response = client.get("/api/providers/FakeProvider/setup-info")
        assert response.status_code == 404

    def test_returns_snaptrade_fields(self, client):
        """Returns field definitions for SnapTrade with optional flags."""
        response = client.get("/api/providers/SnapTrade/setup-info")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 4
        assert data[0]["key"] == "client_id"
        assert data[0]["required"] is True
        assert data[1]["key"] == "consumer_key"
        assert data[1]["required"] is True
        assert data[2]["key"] == "user_id"
        assert data[2]["required"] is False
        assert data[3]["key"] == "user_secret"
        assert data[3]["required"] is False


class TestSetupProvider:
    """Tests for POST /api/providers/{name}/setup."""

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("plaid.api.plaid_api.PlaidApi.link_token_create")
    def test_plaid_setup_success(self, mock_link_create, mock_set_cred, client):
        """Successful Plaid setup returns provider name and message."""
        mock_link_create.return_value = {"link_token": "link-sandbox-test"}

        response = client.post(
            "/api/providers/Plaid/setup",
            json={"credentials": {"client_id": "abc123", "secret": "def456", "environment": "sandbox"}},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["provider"] == "Plaid"
        assert "successfully" in data["message"].lower()

    @patch("services.provider_setup.simplefin_setup.set_credential", return_value=True)
    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_setup_success(self, mock_get_url, mock_set_cred, client):
        """Successful setup returns provider name and message."""
        mock_get_url.return_value = "https://bridge.simplefin.org/access/abc123"

        response = client.post(
            "/api/providers/SimpleFIN/setup",
            json={"credentials": {"setup_token": "dGVzdA=="}},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["provider"] == "SimpleFIN"
        assert "successfully" in data["message"].lower()

    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_invalid_token_400(self, mock_get_url, client):
        """Invalid token returns 400 with error detail."""
        mock_get_url.side_effect = Exception("Invalid setup token")

        response = client.post(
            "/api/providers/SimpleFIN/setup",
            json={"credentials": {"setup_token": "bad-token"}},
        )
        assert response.status_code == 400
        assert "Failed to exchange" in response.json()["detail"]

    def test_empty_credentials_400(self, client):
        """Empty setup token returns 400."""
        response = client.post(
            "/api/providers/SimpleFIN/setup",
            json={"credentials": {"setup_token": ""}},
        )
        assert response.status_code == 400

    def test_unknown_provider_404(self, client):
        """Unknown provider returns 404."""
        response = client.post(
            "/api/providers/FakeProvider/setup",
            json={"credentials": {"key": "value"}},
        )
        assert response.status_code == 404


class TestRemoveCredentials:
    """Tests for DELETE /api/providers/{name}/credentials."""

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_remove_success(self, mock_delete, client):
        """Successful removal returns message."""
        response = client.delete("/api/providers/SimpleFIN/credentials")
        assert response.status_code == 200
        assert "removed" in response.json()["message"].lower()

    def test_unknown_provider_404(self, client):
        """Unknown provider returns 404."""
        response = client.delete("/api/providers/FakeProvider/credentials")
        assert response.status_code == 404

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_remove_snaptrade_credentials(self, mock_delete, client):
        """SnapTrade credential removal succeeds and cleans up user keys."""
        response = client.delete("/api/providers/SnapTrade/credentials")
        assert response.status_code == 200
        assert "removed" in response.json()["message"].lower()
        # Should delete CLIENT_ID, CONSUMER_KEY, USER_ID, USER_SECRET
        assert mock_delete.call_count == 4
