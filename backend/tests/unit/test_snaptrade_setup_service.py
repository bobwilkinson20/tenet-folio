"""Unit tests for the SnapTrade provider setup module."""

from unittest.mock import MagicMock, patch

import pytest

from services.provider_setup_service import SetupResult, validate_and_store


class TestSnapTradeSetup:
    """Tests for SnapTrade validate_and_store()."""

    def test_empty_client_id(self):
        """Empty Client ID raises ValueError."""
        with pytest.raises(ValueError, match="Client ID is required"):
            validate_and_store("SnapTrade", {"client_id": "", "consumer_key": "key"})

    def test_empty_consumer_key(self):
        """Empty Consumer Key raises ValueError."""
        with pytest.raises(ValueError, match="Consumer Key is required"):
            validate_and_store("SnapTrade", {"client_id": "id", "consumer_key": ""})

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("services.provider_setup.snaptrade_setup.set_credential", return_value=True)
    @patch("snaptrade_client.SnapTrade")
    def test_new_user_registration(
        self, mock_snaptrade_cls, mock_set_cred_direct, mock_set_cred_base, mock_get_cred
    ):
        """New user registration stores all 4 credentials."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.body = {"userSecret": "secret123"}
        mock_client.authentication.register_snap_trade_user.return_value = mock_response

        result = validate_and_store(
            "SnapTrade", {"client_id": "cid", "consumer_key": "ckey"}
        )

        assert isinstance(result, SetupResult)
        assert "successfully" in result.message.lower()
        mock_client.authentication.register_snap_trade_user.assert_called_once_with(
            user_id="portfolio-user"
        )
        # Base store_credentials stores CLIENT_ID and CONSUMER_KEY (only API fields)
        assert mock_set_cred_base.call_count == 2
        mock_set_cred_base.assert_any_call("SNAPTRADE_CLIENT_ID", "cid")
        mock_set_cred_base.assert_any_call("SNAPTRADE_CONSUMER_KEY", "ckey")
        # Direct set_credential stores USER_ID and USER_SECRET
        mock_set_cred_direct.assert_any_call("SNAPTRADE_USER_ID", "portfolio-user")
        mock_set_cred_direct.assert_any_call("SNAPTRADE_USER_SECRET", "secret123")

    @patch("services.provider_setup.snaptrade_setup.get_credential")
    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("snaptrade_client.SnapTrade")
    def test_existing_user_revalidation(
        self, mock_snaptrade_cls, mock_set_cred_base, mock_get_cred
    ):
        """Re-setup with existing user validates and preserves existing credentials."""
        mock_get_cred.side_effect = lambda key: {
            "SNAPTRADE_USER_ID": "existing-user",
            "SNAPTRADE_USER_SECRET": "existing-secret",
        }.get(key)

        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client

        result = validate_and_store(
            "SnapTrade", {"client_id": "cid", "consumer_key": "ckey"}
        )

        assert isinstance(result, SetupResult)
        assert "existing user preserved" in result.message.lower()
        mock_client.account_information.list_user_accounts.assert_called_once_with(
            user_id="existing-user",
            user_secret="existing-secret",
        )
        # Should NOT register a new user
        mock_client.authentication.register_snap_trade_user.assert_not_called()
        # Should still store the API credentials (2 fields only)
        assert mock_set_cred_base.call_count == 2

    @patch("services.provider_setup.snaptrade_setup.get_credential")
    @patch("snaptrade_client.SnapTrade")
    def test_existing_user_auth_failure(self, mock_snaptrade_cls, mock_get_cred):
        """Invalid credentials with existing user raises ValueError."""
        mock_get_cred.side_effect = lambda key: {
            "SNAPTRADE_USER_ID": "existing-user",
            "SNAPTRADE_USER_SECRET": "existing-secret",
        }.get(key)

        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_client.account_information.list_user_accounts.side_effect = Exception(
            "401 Unauthorized"
        )

        with pytest.raises(ValueError, match="don't match"):
            validate_and_store(
                "SnapTrade", {"client_id": "wrong", "consumer_key": "wrong"}
            )

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("snaptrade_client.SnapTrade")
    def test_registration_auth_failure(self, mock_snaptrade_cls, mock_get_cred):
        """Registration with invalid API creds raises ValueError."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_client.authentication.register_snap_trade_user.side_effect = Exception(
            "403 Forbidden"
        )

        with pytest.raises(ValueError, match="invalid Client ID"):
            validate_and_store(
                "SnapTrade", {"client_id": "bad", "consumer_key": "bad"}
            )

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("snaptrade_client.SnapTrade")
    def test_registration_user_already_exists(self, mock_snaptrade_cls, mock_get_cred):
        """User already exists error gives actionable message about user secret."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_client.authentication.register_snap_trade_user.side_effect = Exception(
            "(400) User with the following userId already exist: 'portfolio-user'"
        )

        with pytest.raises(ValueError, match="already exists.*User Secret"):
            validate_and_store(
                "SnapTrade", {"client_id": "cid", "consumer_key": "ckey"}
            )

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("services.provider_setup.snaptrade_setup.set_credential", return_value=True)
    @patch("snaptrade_client.SnapTrade")
    def test_form_user_secret_validates_and_stores(
        self, mock_snaptrade_cls, mock_set_cred_direct, mock_set_cred_base, mock_get_cred
    ):
        """Providing user_secret in form validates and stores all credentials."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client

        result = validate_and_store(
            "SnapTrade",
            {"client_id": "cid", "consumer_key": "ckey", "user_secret": "my-secret"},
        )

        assert isinstance(result, SetupResult)
        assert "connections preserved" in result.message.lower()
        mock_client.account_information.list_user_accounts.assert_called_once_with(
            user_id="portfolio-user",
            user_secret="my-secret",
        )
        # Should NOT register a new user
        mock_client.authentication.register_snap_trade_user.assert_not_called()
        # API creds stored via store_credentials
        assert mock_set_cred_base.call_count == 2
        # User creds stored directly
        mock_set_cred_direct.assert_any_call("SNAPTRADE_USER_ID", "portfolio-user")
        mock_set_cred_direct.assert_any_call("SNAPTRADE_USER_SECRET", "my-secret")

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("snaptrade_client.SnapTrade")
    def test_form_user_secret_invalid(self, mock_snaptrade_cls, mock_get_cred):
        """Invalid user_secret in form raises ValueError."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_client.account_information.list_user_accounts.side_effect = Exception(
            "401 Unauthorized"
        )

        with pytest.raises(ValueError, match="don't match|incorrect"):
            validate_and_store(
                "SnapTrade",
                {"client_id": "cid", "consumer_key": "ckey", "user_secret": "wrong"},
            )

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("services.provider_setup.snaptrade_setup.set_credential", return_value=True)
    @patch("snaptrade_client.SnapTrade")
    def test_custom_user_id_with_secret(
        self, mock_snaptrade_cls, mock_set_cred_direct, mock_set_cred_base, mock_get_cred
    ):
        """Custom user_id from form is used for validation and stored."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client

        result = validate_and_store(
            "SnapTrade",
            {
                "client_id": "cid",
                "consumer_key": "ckey",
                "user_id": "portfolio-paper",
                "user_secret": "my-secret",
            },
        )

        assert isinstance(result, SetupResult)
        mock_client.account_information.list_user_accounts.assert_called_once_with(
            user_id="portfolio-paper",
            user_secret="my-secret",
        )
        mock_set_cred_direct.assert_any_call("SNAPTRADE_USER_ID", "portfolio-paper")
        mock_set_cred_direct.assert_any_call("SNAPTRADE_USER_SECRET", "my-secret")

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("services.provider_setup.snaptrade_setup.set_credential", return_value=True)
    @patch("snaptrade_client.SnapTrade")
    def test_custom_user_id_registration(
        self, mock_snaptrade_cls, mock_set_cred_direct, mock_set_cred_base, mock_get_cred
    ):
        """Custom user_id from form is used for registration."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.body = {"userSecret": "new-secret"}
        mock_client.authentication.register_snap_trade_user.return_value = mock_response

        validate_and_store(
            "SnapTrade",
            {"client_id": "cid", "consumer_key": "ckey", "user_id": "portfolio-paper"},
        )

        mock_client.authentication.register_snap_trade_user.assert_called_once_with(
            user_id="portfolio-paper"
        )
        mock_set_cred_direct.assert_any_call("SNAPTRADE_USER_ID", "portfolio-paper")

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("snaptrade_client.SnapTrade")
    def test_registration_generic_error(self, mock_snaptrade_cls, mock_get_cred):
        """Generic registration error raises ValueError."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_client.authentication.register_snap_trade_user.side_effect = Exception(
            "Network error"
        )

        with pytest.raises(ValueError, match="Failed to register"):
            validate_and_store(
                "SnapTrade", {"client_id": "cid", "consumer_key": "ckey"}
            )

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("services.provider_setup.snaptrade_setup.set_credential", return_value=False)
    @patch("snaptrade_client.SnapTrade")
    def test_keychain_failure_user_id(
        self, mock_snaptrade_cls, mock_set_cred_direct, mock_set_cred_base, mock_get_cred
    ):
        """Keychain failure storing USER_ID raises RuntimeError."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.body = {"userSecret": "secret123"}
        mock_client.authentication.register_snap_trade_user.return_value = mock_response

        with pytest.raises(RuntimeError, match="Failed to store SNAPTRADE_USER_ID"):
            validate_and_store(
                "SnapTrade", {"client_id": "cid", "consumer_key": "ckey"}
            )

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("services.provider_setup.base.set_credential", return_value=False)
    @patch("snaptrade_client.SnapTrade")
    def test_keychain_failure_api_creds(self, mock_snaptrade_cls, mock_set_cred_base, mock_get_cred):
        """Keychain failure storing API credentials raises RuntimeError."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.body = {"userSecret": "secret123"}
        mock_client.authentication.register_snap_trade_user.return_value = mock_response

        with pytest.raises(RuntimeError, match="Failed to store"):
            validate_and_store(
                "SnapTrade", {"client_id": "cid", "consumer_key": "ckey"}
            )

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("services.provider_setup.snaptrade_setup.set_credential", return_value=True)
    @patch("snaptrade_client.SnapTrade")
    def test_settings_sync(
        self, mock_snaptrade_cls, mock_set_cred_direct, mock_set_cred_base, mock_get_cred
    ):
        """Setup updates settings singleton for all credentials."""
        from config import settings

        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.body = {"userSecret": "secret123"}
        mock_client.authentication.register_snap_trade_user.return_value = mock_response

        orig_cid = settings.SNAPTRADE_CLIENT_ID
        orig_ckey = settings.SNAPTRADE_CONSUMER_KEY
        orig_uid = settings.SNAPTRADE_USER_ID
        orig_usecret = settings.SNAPTRADE_USER_SECRET

        try:
            validate_and_store(
                "SnapTrade", {"client_id": "newcid", "consumer_key": "newckey"}
            )
            assert settings.SNAPTRADE_CLIENT_ID == "newcid"
            assert settings.SNAPTRADE_CONSUMER_KEY == "newckey"
            assert settings.SNAPTRADE_USER_ID == "portfolio-user"
            assert settings.SNAPTRADE_USER_SECRET == "secret123"
        finally:
            settings.SNAPTRADE_CLIENT_ID = orig_cid
            settings.SNAPTRADE_CONSUMER_KEY = orig_ckey
            settings.SNAPTRADE_USER_ID = orig_uid
            settings.SNAPTRADE_USER_SECRET = orig_usecret

    @patch("services.provider_setup.snaptrade_setup.get_credential", return_value=None)
    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("services.provider_setup.snaptrade_setup.set_credential", return_value=True)
    @patch("snaptrade_client.SnapTrade")
    def test_user_secret_key_alias(
        self, mock_snaptrade_cls, mock_set_cred_direct, mock_set_cred_base, mock_get_cred
    ):
        """Handles 'user_secret' key (snake_case) in registration response."""
        mock_client = MagicMock()
        mock_snaptrade_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.body = {"user_secret": "snake_secret"}
        mock_client.authentication.register_snap_trade_user.return_value = mock_response

        result = validate_and_store(
            "SnapTrade", {"client_id": "cid", "consumer_key": "ckey"}
        )

        assert isinstance(result, SetupResult)
        mock_set_cred_direct.assert_any_call("SNAPTRADE_USER_SECRET", "snake_secret")


class TestSnapTradeRemoveCredentials:
    """Tests for SnapTrade remove_credentials()."""

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_removes_all_four_keys(self, mock_delete):
        """Removes CLIENT_ID, CONSUMER_KEY, USER_ID, and USER_SECRET."""
        from services.provider_setup_service import remove_credentials

        result = remove_credentials("SnapTrade")

        assert mock_delete.call_count == 4
        mock_delete.assert_any_call("SNAPTRADE_CLIENT_ID")
        mock_delete.assert_any_call("SNAPTRADE_CONSUMER_KEY")
        mock_delete.assert_any_call("SNAPTRADE_USER_ID")
        mock_delete.assert_any_call("SNAPTRADE_USER_SECRET")
        assert "removed" in result.lower()
