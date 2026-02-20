"""Tests for services.credential_manager."""

import sys
from unittest.mock import MagicMock, patch

from services.credential_manager import (
    CREDENTIAL_KEYS,
    SERVICE_NAME,
    delete_credential,
    get_credential,
    list_credentials,
    set_credential,
)


# ---------------------------------------------------------------------------
# get_credential
# ---------------------------------------------------------------------------


class TestGetCredential:
    def test_returns_value(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "secret123"
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = get_credential("SNAPTRADE_CLIENT_ID")
        assert result == "secret123"
        mock_keyring.get_password.assert_called_once_with(
            SERVICE_NAME, "SNAPTRADE_CLIENT_ID"
        )

    def test_returns_none_when_not_found(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = get_credential("SNAPTRADE_CLIENT_ID")
        assert result is None

    def test_returns_none_when_keyring_not_installed(self):
        with patch.dict(sys.modules, {"keyring": None}):
            result = get_credential("SNAPTRADE_CLIENT_ID")
        assert result is None

    def test_returns_none_on_keyring_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = Exception("keyring error")
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = get_credential("SNAPTRADE_CLIENT_ID")
        assert result is None


# ---------------------------------------------------------------------------
# set_credential
# ---------------------------------------------------------------------------


class TestSetCredential:
    def test_stores_value(self):
        mock_keyring = MagicMock()
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = set_credential("SNAPTRADE_CLIENT_ID", "secret123")
        assert result is True
        mock_keyring.set_password.assert_called_once_with(
            SERVICE_NAME, "SNAPTRADE_CLIENT_ID", "secret123"
        )

    def test_rejects_non_credential_key(self):
        mock_keyring = MagicMock()
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = set_credential("NOT_A_REAL_KEY", "secret123")
        assert result is False
        mock_keyring.set_password.assert_not_called()

    def test_rejects_empty_value(self):
        mock_keyring = MagicMock()
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            assert set_credential("SNAPTRADE_CLIENT_ID", "") is False
            assert set_credential("SNAPTRADE_CLIENT_ID", "   ") is False
        mock_keyring.set_password.assert_not_called()

    def test_returns_false_when_keyring_not_installed(self):
        with patch.dict(sys.modules, {"keyring": None}):
            result = set_credential("SNAPTRADE_CLIENT_ID", "secret123")
        assert result is False

    def test_returns_false_on_keyring_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.set_password.side_effect = Exception("keyring error")
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = set_credential("SNAPTRADE_CLIENT_ID", "secret123")
        assert result is False


# ---------------------------------------------------------------------------
# delete_credential
# ---------------------------------------------------------------------------


class TestDeleteCredential:
    def test_deletes_value(self):
        mock_keyring = MagicMock()
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = delete_credential("SNAPTRADE_CLIENT_ID")
        assert result is True
        mock_keyring.delete_password.assert_called_once_with(
            SERVICE_NAME, "SNAPTRADE_CLIENT_ID"
        )

    def test_rejects_non_credential_key(self):
        mock_keyring = MagicMock()
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = delete_credential("NOT_A_REAL_KEY")
        assert result is False
        mock_keyring.delete_password.assert_not_called()

    def test_returns_false_when_keyring_not_installed(self):
        with patch.dict(sys.modules, {"keyring": None}):
            result = delete_credential("SNAPTRADE_CLIENT_ID")
        assert result is False

    def test_returns_false_on_keyring_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.delete_password.side_effect = Exception("not found")
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = delete_credential("SNAPTRADE_CLIENT_ID")
        assert result is False


# ---------------------------------------------------------------------------
# list_credentials
# ---------------------------------------------------------------------------


class TestListCredentials:
    def test_lists_stored_credentials(self):
        mock_keyring = MagicMock()

        def fake_get(service, key):
            return {"SNAPTRADE_CLIENT_ID": "cid", "IBKR_FLEX_TOKEN": "tok"}.get(
                key
            )

        mock_keyring.get_password.side_effect = fake_get
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = list_credentials()
        assert result == {"SNAPTRADE_CLIENT_ID": "cid", "IBKR_FLEX_TOKEN": "tok"}

    def test_returns_empty_when_nothing_stored(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = list_credentials()
        assert result == {}


# ---------------------------------------------------------------------------
# CREDENTIAL_KEYS
# ---------------------------------------------------------------------------


class TestCredentialKeys:
    def test_contains_expected_keys(self):
        expected = {
            "SNAPTRADE_CLIENT_ID",
            "SNAPTRADE_CONSUMER_KEY",
            "SNAPTRADE_USER_ID",
            "SNAPTRADE_USER_SECRET",
            "SIMPLEFIN_ACCESS_URL",
            "IBKR_FLEX_TOKEN",
            "IBKR_FLEX_QUERY_ID",
            "COINBASE_API_KEY",
            "COINBASE_API_SECRET",
            "SCHWAB_APP_KEY",
            "SCHWAB_APP_SECRET",
            "SCHWAB_CALLBACK_URL",
            "SQLCIPHER_KEY",
        }
        assert CREDENTIAL_KEYS == expected

    def test_excludes_non_secret_keys(self):
        assert "DATABASE_URL" not in CREDENTIAL_KEYS
        assert "ENVIRONMENT" not in CREDENTIAL_KEYS
        assert "DEBUG" not in CREDENTIAL_KEYS
        assert "LOG_LEVEL" not in CREDENTIAL_KEYS

    def test_excludes_path_keys(self):
        assert "SCHWAB_TOKEN_PATH" not in CREDENTIAL_KEYS
        assert "COINBASE_KEY_FILE" not in CREDENTIAL_KEYS

    def test_is_frozen(self):
        assert isinstance(CREDENTIAL_KEYS, frozenset)
