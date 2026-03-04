"""Unit tests for Schwab provider setup service."""

from unittest.mock import MagicMock, patch

import pytest

from services.provider_setup_service import (
    SetupResult,
    get_setup_fields,
    remove_credentials,
    validate_and_store,
)


class TestSchwabSetupFields:
    """Tests for get_setup_fields('Schwab')."""

    def test_returns_three_fields(self):
        """Schwab returns three fields: app_key, app_secret, callback_url."""
        fields = get_setup_fields("Schwab")
        assert len(fields) == 3
        assert fields[0].key == "app_key"
        assert fields[0].label == "App Key"
        assert fields[0].input_type == "password"
        assert fields[1].key == "app_secret"
        assert fields[1].label == "App Secret"
        assert fields[1].input_type == "password"
        assert fields[2].key == "callback_url"
        assert fields[2].label == "Callback URL"
        assert fields[2].input_type == "text"


class TestSchwabValidateAndStore:
    """Tests for Schwab validate_and_store()."""

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("schwab.auth.get_auth_context")
    def test_success(self, mock_get_auth, mock_set_cred):
        """Successful Schwab setup stores credentials and returns message."""
        mock_ctx = MagicMock()
        mock_get_auth.return_value = mock_ctx

        result = validate_and_store(
            "Schwab",
            {
                "app_key": "my-key",
                "app_secret": "my-secret",
                "callback_url": "https://127.0.0.1",
            },
        )

        assert isinstance(result, SetupResult)
        assert "saved" in result.message.lower() or "credentials" in result.message.lower()
        assert result.warnings == []
        mock_get_auth.assert_called_once_with("my-key", "https://127.0.0.1")
        assert mock_set_cred.call_count == 3
        mock_set_cred.assert_any_call("SCHWAB_APP_KEY", "my-key")
        mock_set_cred.assert_any_call("SCHWAB_APP_SECRET", "my-secret")
        mock_set_cred.assert_any_call("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("schwab.auth.get_auth_context")
    def test_default_callback_url(self, mock_get_auth, mock_set_cred):
        """Empty callback URL defaults to https://127.0.0.1:8000/api/schwab/callback."""
        mock_get_auth.return_value = MagicMock()

        validate_and_store(
            "Schwab",
            {"app_key": "my-key", "app_secret": "my-secret", "callback_url": ""},
        )

        mock_set_cred.assert_any_call("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8000/api/schwab/callback")

    def test_empty_app_key(self):
        """Empty App Key raises ValueError."""
        with pytest.raises(ValueError, match="App Key is required"):
            validate_and_store(
                "Schwab",
                {"app_key": "", "app_secret": "secret", "callback_url": "https://127.0.0.1"},
            )

    def test_empty_app_secret(self):
        """Empty App Secret raises ValueError."""
        with pytest.raises(ValueError, match="App Secret is required"):
            validate_and_store(
                "Schwab",
                {"app_key": "key", "app_secret": "", "callback_url": "https://127.0.0.1"},
            )

    def test_http_callback_url_rejected(self):
        """HTTP (non-HTTPS) callback URL raises ValueError."""
        with pytest.raises(ValueError, match="https://"):
            validate_and_store(
                "Schwab",
                {
                    "app_key": "key",
                    "app_secret": "secret",
                    "callback_url": "http://127.0.0.1",
                },
            )

    @patch.dict("sys.modules", {"schwab": None, "schwab.auth": None})
    def test_schwab_py_not_installed(self):
        """Missing schwab-py raises RuntimeError."""
        with pytest.raises(RuntimeError, match="schwab-py library is not installed"):
            validate_and_store(
                "Schwab",
                {
                    "app_key": "key",
                    "app_secret": "secret",
                    "callback_url": "https://127.0.0.1",
                },
            )

    @patch("services.provider_setup.base.set_credential", return_value=False)
    @patch("schwab.auth.get_auth_context")
    def test_keychain_failure(self, mock_get_auth, mock_set_cred):
        """Keychain storage failure raises RuntimeError."""
        mock_get_auth.return_value = MagicMock()

        with pytest.raises(RuntimeError, match="Failed to store"):
            validate_and_store(
                "Schwab",
                {
                    "app_key": "key",
                    "app_secret": "secret",
                    "callback_url": "https://127.0.0.1",
                },
            )


class TestSchwabRemoveCredentials:
    """Tests for remove_credentials('Schwab')."""

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_removes_credentials_and_token(self, mock_delete):
        """Removes SCHWAB_APP_KEY, SCHWAB_APP_SECRET, SCHWAB_CALLBACK_URL, and SCHWAB_TOKEN."""
        result = remove_credentials("Schwab")

        assert mock_delete.call_count == 4
        mock_delete.assert_any_call("SCHWAB_APP_KEY")
        mock_delete.assert_any_call("SCHWAB_APP_SECRET")
        mock_delete.assert_any_call("SCHWAB_CALLBACK_URL")
        mock_delete.assert_any_call("SCHWAB_TOKEN")
        assert "removed" in result.lower()


class TestSchwabSettingsSync:
    """Tests that validate_and_store syncs the settings singleton."""

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("schwab.auth.get_auth_context")
    def test_schwab_setup_updates_settings(self, mock_get_auth, mock_set_cred):
        """Schwab setup updates settings for all three keys."""
        from config import settings

        mock_get_auth.return_value = MagicMock()

        orig_key = settings.SCHWAB_APP_KEY
        orig_secret = settings.SCHWAB_APP_SECRET
        orig_callback = settings.SCHWAB_CALLBACK_URL

        try:
            validate_and_store(
                "Schwab",
                {
                    "app_key": "new-key",
                    "app_secret": "new-secret",
                    "callback_url": "https://custom.example.com",
                },
            )
            assert settings.SCHWAB_APP_KEY == "new-key"
            assert settings.SCHWAB_APP_SECRET == "new-secret"
            assert settings.SCHWAB_CALLBACK_URL == "https://custom.example.com"
        finally:
            settings.SCHWAB_APP_KEY = orig_key
            settings.SCHWAB_APP_SECRET = orig_secret
            settings.SCHWAB_CALLBACK_URL = orig_callback
