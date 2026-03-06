"""Integration tests for the SnapTrade connection management API endpoints."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.snaptrade import _get_sdk
from main import app


class _MockSDK:
    """Test double for _SnapTradeSDK."""

    def __init__(self):
        self.user_id = "test-user"
        self.user_secret = "test-secret"
        self.client = MagicMock()


def _make_client(mock_sdk: _MockSDK) -> TestClient:
    """Create a TestClient with the SDK dependency overridden."""
    app.dependency_overrides[_get_sdk] = lambda: mock_sdk
    client = TestClient(app)
    return client


def _cleanup():
    app.dependency_overrides.pop(_get_sdk, None)


class TestListConnections:
    """Tests for GET /api/snaptrade/connections."""

    def test_returns_connections(self):
        """Returns formatted list of brokerage authorizations."""
        sdk = _MockSDK()
        sdk.client.connections.list_brokerage_authorizations.return_value = [
            {
                "id": "auth-1",
                "brokerage": {"name": "Alpaca"},
                "name": "My Alpaca",
                "disabled": False,
                "disabled_date": None,
                "meta": None,
            },
            {
                "id": "auth-2",
                "brokerage": {"name": "Questrade"},
                "name": "Questrade TFSA",
                "disabled": True,
                "disabled_date": "2026-01-15",
                "meta": {"status_message": "Token expired"},
            },
        ]

        client = _make_client(sdk)
        try:
            response = client.get("/api/snaptrade/connections")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 2
            assert data[0]["authorization_id"] == "auth-1"
            assert data[0]["brokerage_name"] == "Alpaca"
            assert data[0]["name"] == "My Alpaca"
            assert data[0]["disabled"] is False
            assert data[0]["error_message"] is None

            assert data[1]["authorization_id"] == "auth-2"
            assert data[1]["disabled"] is True
            assert data[1]["disabled_date"] == "2026-01-15"
            assert data[1]["error_message"] == "Token expired"
        finally:
            _cleanup()

    def test_returns_empty_list(self):
        """Returns empty list when no connections exist."""
        sdk = _MockSDK()
        sdk.client.connections.list_brokerage_authorizations.return_value = []

        client = _make_client(sdk)
        try:
            response = client.get("/api/snaptrade/connections")
            assert response.status_code == 200
            assert response.json() == []
        finally:
            _cleanup()

    def test_sdk_error(self):
        """SDK error returns 500."""
        sdk = _MockSDK()
        sdk.client.connections.list_brokerage_authorizations.side_effect = Exception("SDK error")

        client = _make_client(sdk)
        try:
            response = client.get("/api/snaptrade/connections")
            assert response.status_code == 500
            assert "Failed to list" in response.json()["detail"]
        finally:
            _cleanup()

    def test_unconfigured_returns_400(self):
        """Missing credentials returns 400."""
        # Don't override the SDK — let the real dependency try to read credentials
        app.dependency_overrides.pop(_get_sdk, None)
        with patch("services.credential_manager.get_credential", return_value=None):
            client = TestClient(app)
            response = client.get("/api/snaptrade/connections")
            assert response.status_code == 400
            assert "not configured" in response.json()["detail"].lower()


class TestCreateConnectUrl:
    """Tests for POST /api/snaptrade/connect-url."""

    def test_returns_redirect_url(self):
        """Returns redirect URL from login response."""
        sdk = _MockSDK()
        mock_response = MagicMock()
        mock_response.body = {"redirectURI": "https://app.snaptrade.com/connect?token=abc"}
        sdk.client.authentication.login_snap_trade_user.return_value = mock_response

        client = _make_client(sdk)
        try:
            response = client.post("/api/snaptrade/connect-url")
            assert response.status_code == 200
            assert response.json()["redirect_url"] == "https://app.snaptrade.com/connect?token=abc"
        finally:
            _cleanup()

    def test_handles_redirect_uri_key(self):
        """Handles 'redirect_uri' (snake_case) key in response."""
        sdk = _MockSDK()
        mock_response = MagicMock()
        mock_response.body = {"redirect_uri": "https://app.snaptrade.com/connect?token=def"}
        sdk.client.authentication.login_snap_trade_user.return_value = mock_response

        client = _make_client(sdk)
        try:
            response = client.post("/api/snaptrade/connect-url")
            assert response.status_code == 200
            assert "token=def" in response.json()["redirect_url"]
        finally:
            _cleanup()

    def test_handles_login_redirect_uri_key(self):
        """Handles 'loginRedirectURI' key in response."""
        sdk = _MockSDK()
        mock_response = MagicMock()
        mock_response.body = {"loginRedirectURI": "https://app.snaptrade.com/connect?token=ghi"}
        sdk.client.authentication.login_snap_trade_user.return_value = mock_response

        client = _make_client(sdk)
        try:
            response = client.post("/api/snaptrade/connect-url")
            assert response.status_code == 200
            assert "token=ghi" in response.json()["redirect_url"]
        finally:
            _cleanup()

    def test_sdk_error(self):
        """SDK error returns 500."""
        sdk = _MockSDK()
        sdk.client.authentication.login_snap_trade_user.side_effect = Exception("Network error")

        client = _make_client(sdk)
        try:
            response = client.post("/api/snaptrade/connect-url")
            assert response.status_code == 500
            assert "Failed to generate" in response.json()["detail"]
        finally:
            _cleanup()


class TestRemoveConnection:
    """Tests for DELETE /api/snaptrade/connections/{authorization_id}."""

    def test_removes_connection(self):
        """Successfully removes a connection."""
        sdk = _MockSDK()
        client = _make_client(sdk)
        try:
            response = client.delete("/api/snaptrade/connections/auth-1")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "ok"
            assert data["authorization_id"] == "auth-1"
            sdk.client.connections.remove_brokerage_authorization.assert_called_once_with(
                authorization_id="auth-1",
                user_id="test-user",
                user_secret="test-secret",
            )
        finally:
            _cleanup()

    def test_sdk_error(self):
        """SDK error returns 500."""
        sdk = _MockSDK()
        sdk.client.connections.remove_brokerage_authorization.side_effect = Exception("Not found")

        client = _make_client(sdk)
        try:
            response = client.delete("/api/snaptrade/connections/bad-id")
            assert response.status_code == 500
            assert "Failed to remove" in response.json()["detail"]
        finally:
            _cleanup()


class TestRefreshConnection:
    """Tests for POST /api/snaptrade/connections/{authorization_id}/refresh."""

    def test_returns_reconnect_url(self):
        """Returns reconnect URL for re-authenticating a connection."""
        sdk = _MockSDK()
        mock_response = MagicMock()
        mock_response.body = {"redirectURI": "https://app.snaptrade.com/reconnect?token=xyz"}
        sdk.client.authentication.login_snap_trade_user.return_value = mock_response

        client = _make_client(sdk)
        try:
            response = client.post("/api/snaptrade/connections/auth-1/refresh")
            assert response.status_code == 200

            data = response.json()
            assert data["redirect_url"] == "https://app.snaptrade.com/reconnect?token=xyz"
            assert data["authorization_id"] == "auth-1"
            sdk.client.authentication.login_snap_trade_user.assert_called_once_with(
                user_id="test-user",
                user_secret="test-secret",
                reconnect="auth-1",
            )
        finally:
            _cleanup()

    def test_sdk_error(self):
        """SDK error returns 500."""
        sdk = _MockSDK()
        sdk.client.authentication.login_snap_trade_user.side_effect = Exception("Error")

        client = _make_client(sdk)
        try:
            response = client.post("/api/snaptrade/connections/bad-id/refresh")
            assert response.status_code == 500
            assert "Failed to generate reconnect" in response.json()["detail"]
        finally:
            _cleanup()
