"""Unit tests for the Schwab OAuth API endpoints."""

import time
from unittest.mock import MagicMock, patch

from api.schwab import _auth_contexts, AUTH_CONTEXT_TTL


class TestCreateAuthUrl:
    """Tests for POST /api/schwab/auth-url."""

    def setup_method(self):
        _auth_contexts.clear()

    @patch("api.schwab.settings")
    @patch("schwab.auth.get_auth_context")
    def test_success(self, mock_get_auth, mock_settings, client):
        """Returns authorization URL and state on success."""
        mock_settings.SCHWAB_APP_KEY = "my-key"
        mock_settings.SCHWAB_CALLBACK_URL = "https://127.0.0.1"

        mock_ctx = MagicMock()
        mock_ctx.authorization_url = "https://schwab.example.com/authorize?state=abc"
        mock_ctx.state = "abc123"
        mock_get_auth.return_value = mock_ctx

        response = client.post("/api/schwab/auth-url")

        assert response.status_code == 200
        data = response.json()
        assert data["authorization_url"] == "https://schwab.example.com/authorize?state=abc"
        assert data["state"] == "abc123"
        mock_get_auth.assert_called_once_with("my-key", "https://127.0.0.1")

    @patch("api.schwab.settings")
    def test_unconfigured(self, mock_settings, client):
        """Returns 400 when Schwab is not configured."""
        mock_settings.SCHWAB_APP_KEY = ""
        mock_settings.SCHWAB_CALLBACK_URL = ""

        response = client.post("/api/schwab/auth-url")

        assert response.status_code == 400
        assert "not configured" in response.json()["detail"].lower()


class TestExchangeToken:
    """Tests for POST /api/schwab/exchange-token."""

    def setup_method(self):
        _auth_contexts.clear()

    @patch("api.schwab.settings")
    @patch("schwab.auth.client_from_received_url")
    def test_success(self, mock_exchange, mock_settings, client):
        """Successful token exchange returns message and account count."""
        mock_settings.SCHWAB_APP_KEY = "my-key"
        mock_settings.SCHWAB_APP_SECRET = "my-secret"
        # (token stored in Keychain, no SCHWAB_TOKEN_PATH needed)

        # Pre-populate auth context
        mock_ctx = MagicMock()
        _auth_contexts["test-state"] = (mock_ctx, time.time())

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"accountNumber": "123"}, {"accountNumber": "456"}]
        mock_client.get_account_numbers.return_value = mock_resp
        mock_exchange.return_value = mock_client

        response = client.post(
            "/api/schwab/exchange-token",
            json={"state": "test-state", "received_url": "https://127.0.0.1?code=xyz&session=test-state"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["account_count"] == 2
        assert "2 account(s)" in data["message"]

    def test_invalid_state(self, client):
        """Invalid state returns 400."""
        response = client.post(
            "/api/schwab/exchange-token",
            json={"state": "nonexistent", "received_url": "https://127.0.0.1?code=xyz"},
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower() or "expired" in response.json()["detail"].lower()

    def test_expired_context(self, client):
        """Expired auth context is cleaned up and returns 400."""
        mock_ctx = MagicMock()
        # Set creation time well in the past — cleanup removes it before lookup
        _auth_contexts["expired-state"] = (mock_ctx, time.time() - AUTH_CONTEXT_TTL - 100)

        response = client.post(
            "/api/schwab/exchange-token",
            json={"state": "expired-state", "received_url": "https://127.0.0.1?code=xyz"},
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()
        assert "expired-state" not in _auth_contexts


class TestTokenStatus:
    """Tests for GET /api/schwab/token-status."""

    def setup_method(self):
        _auth_contexts.clear()

    @patch("api.schwab.settings")
    def test_no_credentials(self, mock_settings, client):
        """Returns no_credentials when Schwab is not configured."""
        mock_settings.SCHWAB_APP_KEY = ""
        mock_settings.SCHWAB_APP_SECRET = ""

        response = client.get("/api/schwab/token-status")

        assert response.status_code == 200
        assert response.json()["status"] == "no_credentials"

    @patch("api.schwab.read_token_from_keychain", return_value=None)
    @patch("api.schwab.settings")
    def test_no_token(self, mock_settings, _mock_read, client):
        """Returns no_token when no token in Keychain."""
        mock_settings.SCHWAB_APP_KEY = "key"
        mock_settings.SCHWAB_APP_SECRET = "secret"

        response = client.get("/api/schwab/token-status")

        assert response.status_code == 200
        assert response.json()["status"] == "no_token"

    @patch("api.schwab.read_token_from_keychain")
    @patch("api.schwab.settings")
    def test_valid_token(self, mock_settings, mock_read, client):
        """Returns valid for a token created 2 days ago."""
        mock_settings.SCHWAB_APP_KEY = "key"
        mock_settings.SCHWAB_APP_SECRET = "secret"

        two_days_ago = time.time() - (2 * 86400)
        mock_read.return_value = {"creation_timestamp": two_days_ago}

        response = client.get("/api/schwab/token-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "valid"
        assert data["days_remaining"] is not None
        assert data["days_remaining"] > 4.0

    @patch("api.schwab.read_token_from_keychain")
    @patch("api.schwab.settings")
    def test_expiring_soon(self, mock_settings, mock_read, client):
        """Returns expiring_soon for a token created 5.5 days ago."""
        mock_settings.SCHWAB_APP_KEY = "key"
        mock_settings.SCHWAB_APP_SECRET = "secret"

        five_and_half_days_ago = time.time() - (5.5 * 86400)
        mock_read.return_value = {"creation_timestamp": five_and_half_days_ago}

        response = client.get("/api/schwab/token-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "expiring_soon"
        assert data["days_remaining"] is not None
        assert data["days_remaining"] < 2.0

    @patch("api.schwab.read_token_from_keychain")
    @patch("api.schwab.settings")
    def test_expired(self, mock_settings, mock_read, client):
        """Returns expired for a token created 8 days ago."""
        mock_settings.SCHWAB_APP_KEY = "key"
        mock_settings.SCHWAB_APP_SECRET = "secret"

        eight_days_ago = time.time() - (8 * 86400)
        mock_read.return_value = {"creation_timestamp": eight_days_ago}

        response = client.get("/api/schwab/token-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "expired"


class TestOAuthCallback:
    """Tests for GET /api/schwab/callback.

    Schwab redirects with ``code``, ``session`` (Schwab's internal ID),
    and ``state`` (our OAuth CSRF token).  The callback looks up the
    pending auth context by ``state``.
    """

    def setup_method(self):
        """Clear leaked auth contexts from other test classes."""
        _auth_contexts.clear()

    @patch("api.schwab.settings")
    @patch("schwab.auth.client_from_received_url")
    def test_success_returns_html(self, mock_exchange, mock_settings, client):
        """Successful callback returns self-closing HTML page."""
        mock_settings.SCHWAB_APP_KEY = "my-key"
        mock_settings.SCHWAB_APP_SECRET = "my-secret"
        mock_settings.SCHWAB_CALLBACK_URL = "https://127.0.0.1"
        # (token stored in Keychain, no SCHWAB_TOKEN_PATH needed)

        mock_ctx = MagicMock()
        _auth_contexts["our-state-abc"] = (mock_ctx, time.time())
        mock_exchange.return_value = MagicMock()

        response = client.get(
            "/api/schwab/callback",
            params={
                "code": "auth-code",
                "session": "schwab-session-xyz",
                "state": "our-state-abc",
            },
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Schwab Authorized" in response.text
        assert "window.close()" in response.text

    def test_missing_code_returns_error_html(self, client):
        """Missing code returns error HTML page."""
        response = client.get("/api/schwab/callback")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Authorization Failed" in response.text

    def test_no_matching_state_returns_error_html(self, client):
        """Unrecognized state returns error HTML page."""
        response = client.get(
            "/api/schwab/callback",
            params={"code": "auth-code", "session": "s", "state": "unknown"},
        )

        assert response.status_code == 200
        assert "Authorization Failed" in response.text
        assert "Invalid or expired" in response.text

    def test_expired_context_not_used(self, client):
        """Expired auth context is cleaned up and not matched."""
        mock_ctx = MagicMock()
        _auth_contexts["old-state"] = (mock_ctx, time.time() - AUTH_CONTEXT_TTL - 100)

        response = client.get(
            "/api/schwab/callback",
            params={"code": "auth-code", "session": "s", "state": "old-state"},
        )

        assert response.status_code == 200
        assert "Authorization Failed" in response.text
        assert "Invalid or expired" in response.text

    @patch("api.schwab.settings")
    @patch("schwab.auth.client_from_received_url")
    def test_exchange_failure_returns_error_html(self, mock_exchange, mock_settings, client):
        """Token exchange failure returns error HTML page."""
        mock_settings.SCHWAB_APP_KEY = "my-key"
        mock_settings.SCHWAB_APP_SECRET = "my-secret"
        mock_settings.SCHWAB_CALLBACK_URL = "https://127.0.0.1"
        # (token stored in Keychain, no SCHWAB_TOKEN_PATH needed)

        mock_ctx = MagicMock()
        _auth_contexts["pending-state"] = (mock_ctx, time.time())
        mock_exchange.side_effect = Exception("Bad code")

        response = client.get(
            "/api/schwab/callback",
            params={"code": "bad-code", "session": "s", "state": "pending-state"},
        )

        assert response.status_code == 200
        assert "Authorization Failed" in response.text
        assert "Token exchange failed" in response.text

    @patch("api.schwab.settings")
    @patch("schwab.auth.client_from_received_url")
    def test_context_cleaned_up_after_success(self, mock_exchange, mock_settings, client):
        """Successful callback removes the used auth context."""
        mock_settings.SCHWAB_APP_KEY = "my-key"
        mock_settings.SCHWAB_APP_SECRET = "my-secret"
        mock_settings.SCHWAB_CALLBACK_URL = "https://127.0.0.1"
        # (token stored in Keychain, no SCHWAB_TOKEN_PATH needed)

        mock_ctx = MagicMock()
        _auth_contexts["used-state"] = (mock_ctx, time.time())
        mock_exchange.return_value = MagicMock()

        response = client.get(
            "/api/schwab/callback",
            params={"code": "auth-code", "session": "s", "state": "used-state"},
        )

        assert response.status_code == 200
        assert "Schwab Authorized" in response.text
        assert "used-state" not in _auth_contexts
