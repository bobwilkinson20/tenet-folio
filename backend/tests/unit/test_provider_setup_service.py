"""Unit tests for the provider setup service."""

from unittest.mock import MagicMock, patch

import pytest

from services.provider_setup_service import (
    SetupResult,
    get_setup_fields,
    remove_credentials,
    validate_and_store,
)


class TestGetSetupFields:
    """Tests for get_setup_fields()."""

    def test_returns_simplefin_fields(self):
        """SimpleFIN returns one field: setup_token."""
        fields = get_setup_fields("SimpleFIN")
        assert len(fields) == 1
        assert fields[0].key == "setup_token"
        assert fields[0].label == "Setup Token"
        assert fields[0].input_type == "password"
        assert fields[0].help_text  # non-empty

    def test_returns_ibkr_fields(self):
        """IBKR returns two fields: flex_token and flex_query_id."""
        fields = get_setup_fields("IBKR")
        assert len(fields) == 2
        assert fields[0].key == "flex_token"
        assert fields[0].label == "Flex Token"
        assert fields[0].input_type == "password"
        assert fields[1].key == "flex_query_id"
        assert fields[1].label == "Flex Query ID"
        assert fields[1].input_type == "text"

    def test_returns_coinbase_fields(self):
        """Coinbase returns two fields: api_key and api_secret (textarea)."""
        fields = get_setup_fields("Coinbase")
        assert len(fields) == 2
        assert fields[0].key == "api_key"
        assert fields[0].label == "API Key"
        assert fields[0].input_type == "password"
        assert fields[1].key == "api_secret"
        assert fields[1].label == "API Secret"
        assert fields[1].input_type == "textarea"

    def test_unknown_provider_raises(self):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="No setup configuration"):
            get_setup_fields("UnknownProvider")

    def test_returns_snaptrade_fields(self):
        """SnapTrade returns four fields: client_id, consumer_key, user_id, user_secret."""
        fields = get_setup_fields("SnapTrade")
        assert len(fields) == 4
        assert fields[0].key == "client_id"
        assert fields[0].label == "Client ID"
        assert fields[0].input_type == "password"
        assert fields[1].key == "consumer_key"
        assert fields[1].label == "Consumer Key"
        assert fields[1].input_type == "password"
        assert fields[2].key == "user_id"
        assert "optional" in fields[2].label.lower()
        assert fields[2].input_type == "text"
        assert fields[3].key == "user_secret"
        assert "optional" in fields[3].label.lower()
        assert fields[3].input_type == "password"


class TestValidateAndStore:
    """Tests for validate_and_store()."""

    @patch("services.provider_setup.simplefin_setup.set_credential", return_value=True)
    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_success(self, mock_get_url, mock_set_cred):
        """Successful SimpleFIN setup exchanges token and stores access URL."""
        mock_get_url.return_value = "https://bridge.simplefin.org/access/abc123"

        result = validate_and_store("SimpleFIN", {"setup_token": "dGVzdA=="})

        assert isinstance(result, SetupResult)
        mock_get_url.assert_called_once_with("dGVzdA==")
        mock_set_cred.assert_called_once_with(
            "SIMPLEFIN_ACCESS_URL", "https://bridge.simplefin.org/access/abc123"
        )
        assert "successfully" in result.message.lower()
        assert result.warnings == []

    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_invalid_token(self, mock_get_url):
        """Invalid/used token raises ValueError with 'already been used' hint."""
        mock_get_url.side_effect = Exception("Invalid setup token")

        with pytest.raises(ValueError, match="may have already been used"):
            validate_and_store("SimpleFIN", {"setup_token": "bad-token"})

    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_network_error(self, mock_get_url):
        """Network error raises ValueError with connectivity hint."""
        import httpx

        mock_get_url.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(ValueError, match="could not reach SimpleFIN"):
            validate_and_store("SimpleFIN", {"setup_token": "dGVzdA=="})

    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_bad_token_format(self, mock_get_url):
        """Malformed base64 token raises ValueError with format hint."""
        mock_get_url.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "bad")

        with pytest.raises(ValueError, match="invalid format"):
            validate_and_store("SimpleFIN", {"setup_token": "not-base64!"})

    def test_simplefin_empty_token(self):
        """Empty setup token raises ValueError."""
        with pytest.raises(ValueError, match="Setup token is required"):
            validate_and_store("SimpleFIN", {"setup_token": ""})

    def test_simplefin_missing_token(self):
        """Missing setup_token key raises ValueError."""
        with pytest.raises(ValueError, match="Setup token is required"):
            validate_and_store("SimpleFIN", {})

    @patch("services.provider_setup.simplefin_setup.set_credential", return_value=False)
    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_keychain_failure(self, mock_get_url, mock_set_cred):
        """Keychain storage failure raises RuntimeError."""
        mock_get_url.return_value = "https://bridge.simplefin.org/access/abc123"

        with pytest.raises(RuntimeError, match="Failed to store credentials"):
            validate_and_store("SimpleFIN", {"setup_token": "dGVzdA=="})

    def test_unknown_provider_raises(self):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="No setup configuration"):
            validate_and_store("UnknownProvider", {"key": "val"})

    @patch(
        "services.provider_setup.registry.PROVIDER_CREDENTIAL_MAP",
        {"TestProvider": [{"key": "tok", "store_key": "TOK", "label": "Token", "help_text": "", "input_type": "text"}]},
    )
    def test_provider_in_map_but_no_validator_raises(self):
        """Provider in PROVIDER_CREDENTIAL_MAP but not in _VALIDATORS raises ValueError."""
        with pytest.raises(ValueError, match="No validator implemented"):
            validate_and_store("TestProvider", {"tok": "value"})

    @patch.dict("sys.modules", {"simplefin": None})
    def test_simplefin_library_not_installed(self):
        """Missing simplefin library raises RuntimeError with helpful message."""
        with pytest.raises(RuntimeError, match="SimpleFIN library is not installed"):
            validate_and_store("SimpleFIN", {"setup_token": "dGVzdA=="})

    # --- IBKR tests ---

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("scripts.setup_ibkr.validate_trade_columns", return_value=([], []))
    @patch("scripts.setup_ibkr.validate_query_sections", return_value=[])
    @patch("ibflex.client.download", return_value=b"<xml>report</xml>")
    def test_ibkr_success(
        self, mock_download, mock_sections, mock_columns, mock_set_cred
    ):
        """Successful IBKR setup validates and stores both credentials."""
        result = validate_and_store(
            "IBKR", {"flex_token": "tok123", "flex_query_id": "456"}
        )

        assert isinstance(result, SetupResult)
        assert "successfully" in result.message.lower()
        assert result.warnings == []
        mock_download.assert_called_once_with("tok123", "456")
        mock_sections.assert_called_once_with(b"<xml>report</xml>")
        mock_columns.assert_called_once_with(b"<xml>report</xml>")
        assert mock_set_cred.call_count == 2
        mock_set_cred.assert_any_call("IBKR_FLEX_TOKEN", "tok123")
        mock_set_cred.assert_any_call("IBKR_FLEX_QUERY_ID", "456")

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch(
        "scripts.setup_ibkr.validate_trade_columns",
        return_value=([], ["buySell", "netCash"]),
    )
    @patch("scripts.setup_ibkr.validate_query_sections", return_value=[])
    @patch("ibflex.client.download", return_value=b"<xml>report</xml>")
    def test_ibkr_success_with_warnings(
        self, mock_download, mock_sections, mock_columns, mock_set_cred
    ):
        """Valid IBKR setup with missing recommended columns returns warnings."""
        result = validate_and_store(
            "IBKR", {"flex_token": "tok123", "flex_query_id": "456"}
        )

        assert isinstance(result, SetupResult)
        assert "successfully" in result.message.lower()
        assert len(result.warnings) == 1
        assert "buySell" in result.warnings[0]
        assert "netCash" in result.warnings[0]
        assert mock_set_cred.call_count == 2

    @patch("scripts.setup_ibkr.validate_query_sections", return_value=["Open Positions", "Cash Report"])
    @patch("ibflex.client.download", return_value=b"<xml>report</xml>")
    def test_ibkr_missing_sections(self, mock_download, mock_sections):
        """Missing required sections raises ValueError listing sections and their columns."""
        with pytest.raises(ValueError, match="missing required sections") as exc_info:
            validate_and_store(
                "IBKR", {"flex_token": "tok123", "flex_query_id": "456"}
            )
        msg = str(exc_info.value)
        assert "Open Positions (columns:" in msg
        assert "Cash Report (columns:" in msg
        assert "Symbol" in msg
        assert "EndingCash" in msg

    @patch(
        "scripts.setup_ibkr.validate_trade_columns",
        return_value=(["tradeID"], []),
    )
    @patch("scripts.setup_ibkr.validate_query_sections", return_value=[])
    @patch("ibflex.client.download", return_value=b"<xml>report</xml>")
    def test_ibkr_missing_required_columns(
        self, mock_download, mock_sections, mock_columns
    ):
        """Missing required trade columns raises ValueError."""
        with pytest.raises(ValueError, match="missing required columns.*tradeID"):
            validate_and_store(
                "IBKR", {"flex_token": "tok123", "flex_query_id": "456"}
            )

    def test_ibkr_empty_token(self):
        """Empty Flex Token raises ValueError."""
        with pytest.raises(ValueError, match="Flex Token is required"):
            validate_and_store("IBKR", {"flex_token": "", "flex_query_id": "456"})

    def test_ibkr_empty_query_id(self):
        """Empty Flex Query ID raises ValueError."""
        with pytest.raises(ValueError, match="Flex Query ID is required"):
            validate_and_store("IBKR", {"flex_token": "tok123", "flex_query_id": ""})

    @patch("ibflex.client.download", side_effect=Exception("Invalid token"))
    def test_ibkr_invalid_credentials(self, mock_download):
        """ibflex download error raises ValueError with actionable message."""
        with pytest.raises(ValueError, match="Failed to validate IBKR credentials"):
            validate_and_store(
                "IBKR", {"flex_token": "bad", "flex_query_id": "bad"}
            )

    def test_ibkr_download_timeout(self):
        """Download timeout raises ValueError with timeout message."""
        from concurrent.futures import TimeoutError as FuturesTimeoutError

        with patch(
            "services.provider_setup.ibkr_setup.ThreadPoolExecutor"
        ) as mock_pool_cls:
            mock_executor = MagicMock()
            mock_pool_cls.return_value = mock_executor
            mock_executor.submit.return_value.result.side_effect = FuturesTimeoutError()

            with pytest.raises(ValueError, match="timed out"):
                validate_and_store(
                    "IBKR", {"flex_token": "tok123", "flex_query_id": "456"}
                )
            mock_executor.shutdown.assert_called_once_with(wait=False)

    @patch("services.provider_setup.base.set_credential")
    @patch("scripts.setup_ibkr.validate_trade_columns", return_value=([], []))
    @patch("scripts.setup_ibkr.validate_query_sections", return_value=[])
    @patch("ibflex.client.download", return_value=b"<xml>report</xml>")
    def test_ibkr_keychain_failure(
        self, mock_download, mock_sections, mock_columns, mock_set_cred
    ):
        """Keychain storage failure raises RuntimeError."""
        mock_set_cred.return_value = False

        with pytest.raises(RuntimeError, match="Failed to store"):
            validate_and_store(
                "IBKR", {"flex_token": "tok123", "flex_query_id": "456"}
            )

    # --- Coinbase tests ---

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("coinbase.rest.RESTClient")
    def test_coinbase_success(self, mock_rest_cls, mock_set_cred):
        """Successful Coinbase setup validates and stores both credentials."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client

        result = validate_and_store(
            "Coinbase",
            {"api_key": "organizations/org1/apiKeys/key1", "api_secret": "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----"},
        )

        assert isinstance(result, SetupResult)
        assert "successfully" in result.message.lower()
        assert result.warnings == []
        mock_rest_cls.assert_called_once()
        mock_client.get_accounts.assert_called_once_with(limit=1)
        assert mock_set_cred.call_count == 2
        mock_set_cred.assert_any_call("COINBASE_API_KEY", "organizations/org1/apiKeys/key1")
        mock_set_cred.assert_any_call("COINBASE_API_SECRET", "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----")

    def test_coinbase_empty_api_key(self):
        """Empty API Key raises ValueError."""
        with pytest.raises(ValueError, match="API Key is required"):
            validate_and_store("Coinbase", {"api_key": "", "api_secret": "secret"})

    def test_coinbase_empty_api_secret(self):
        """Empty API Secret raises ValueError."""
        with pytest.raises(ValueError, match="API Secret is required"):
            validate_and_store("Coinbase", {"api_key": "key1", "api_secret": ""})

    @patch("coinbase.rest.RESTClient")
    def test_coinbase_ed25519_error(self, mock_rest_cls):
        """Ed25519 key type error is mapped to helpful ECDSA message."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client
        mock_client.get_accounts.side_effect = Exception("Could not deserialize key data")

        with pytest.raises(ValueError, match="ECDSA"):
            validate_and_store(
                "Coinbase",
                {"api_key": "key1", "api_secret": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"},
            )

    @patch("coinbase.rest.RESTClient")
    def test_coinbase_auth_failure(self, mock_rest_cls):
        """Authentication failure is mapped to helpful message."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client
        mock_client.get_accounts.side_effect = Exception("401 Unauthorized")

        with pytest.raises(ValueError, match="invalid API key or secret"):
            validate_and_store(
                "Coinbase",
                {"api_key": "key1", "api_secret": "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----"},
            )

    @patch("coinbase.rest.RESTClient")
    def test_coinbase_invalid_key_format(self, mock_rest_cls):
        """Invalid key format error is mapped to helpful credential format message."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client
        mock_client.get_accounts.side_effect = Exception("invalid api key format")

        with pytest.raises(ValueError, match="Invalid credential format"):
            validate_and_store(
                "Coinbase",
                {"api_key": "bad-format", "api_secret": "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----"},
            )

    @patch("coinbase.rest.RESTClient")
    def test_coinbase_generic_error_not_caught_by_invalid_branch(self, mock_rest_cls):
        """Generic errors with 'invalid' in unrelated context fall through to the generic handler."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client
        mock_client.get_accounts.side_effect = Exception("invalid JSON response from server")

        with pytest.raises(ValueError, match="Failed to validate Coinbase credentials"):
            validate_and_store(
                "Coinbase",
                {"api_key": "key1", "api_secret": "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----"},
            )

    @patch("coinbase.rest.RESTClient")
    def test_coinbase_invalid_key_size_falls_through(self, mock_rest_cls):
        """OpenSSL 'invalid key size' error falls through to generic handler, not credential format."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client
        mock_client.get_accounts.side_effect = Exception("invalid key size")

        with pytest.raises(ValueError, match="Failed to validate Coinbase credentials"):
            validate_and_store(
                "Coinbase",
                {"api_key": "key1", "api_secret": "-----BEGIN EC PRIVATE KEY-----\ntruncated\n-----END EC PRIVATE KEY-----"},
            )

    @patch("services.provider_setup.base.set_credential", return_value=False)
    @patch("coinbase.rest.RESTClient")
    def test_coinbase_keychain_failure(self, mock_rest_cls, mock_set_cred):
        """Keychain storage failure raises RuntimeError."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="Failed to store"):
            validate_and_store(
                "Coinbase",
                {"api_key": "key1", "api_secret": "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----"},
            )

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("coinbase.rest.RESTClient")
    def test_coinbase_normalizes_pem_newlines(self, mock_rest_cls, mock_set_cred):
        """Literal \\n in PEM secret is converted to real newlines before storage."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client

        validate_and_store(
            "Coinbase",
            {
                "api_key": "key1",
                "api_secret": "-----BEGIN EC PRIVATE KEY-----\\ntest\\n-----END EC PRIVATE KEY-----",
            },
        )

        # The stored secret should have real newlines, not literal \n
        mock_set_cred.assert_any_call(
            "COINBASE_API_SECRET",
            "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----",
        )

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("coinbase.rest.RESTClient")
    def test_coinbase_normalizes_crlf_line_endings(self, mock_rest_cls, mock_set_cred):
        """Windows CRLF line endings in PEM secret are normalized to LF."""
        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client

        validate_and_store(
            "Coinbase",
            {
                "api_key": "key1",
                "api_secret": "-----BEGIN EC PRIVATE KEY-----\r\ntest\r\n-----END EC PRIVATE KEY-----",
            },
        )

        mock_set_cred.assert_any_call(
            "COINBASE_API_SECRET",
            "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----",
        )


    # --- Plaid tests ---

    def test_returns_plaid_fields(self):
        """Plaid returns three fields: client_id, secret, and environment (select)."""
        fields = get_setup_fields("Plaid")
        assert len(fields) == 3
        assert fields[0].key == "client_id"
        assert fields[0].label == "Client ID"
        assert fields[0].input_type == "password"
        assert fields[1].key == "secret"
        assert fields[1].label == "Secret"
        assert fields[1].input_type == "password"
        assert fields[2].key == "environment"
        assert fields[2].label == "Environment"
        assert fields[2].input_type == "select"
        assert len(fields[2].options) == 2
        assert fields[2].options[0]["value"] == "sandbox"
        assert fields[2].options[1]["value"] == "production"


class TestValidateAndStorePlaid:
    """Tests for Plaid validate_and_store()."""

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("plaid.api.plaid_api.PlaidApi.link_token_create")
    def test_plaid_success(self, mock_link_create, mock_set_cred):
        """Successful Plaid setup validates and stores all three credentials."""
        mock_link_create.return_value = {"link_token": "link-sandbox-test"}

        result = validate_and_store(
            "Plaid",
            {"client_id": "abc123", "secret": "def456", "environment": "sandbox"},
        )

        assert isinstance(result, SetupResult)
        assert "successfully" in result.message.lower()
        assert result.warnings == []
        assert mock_set_cred.call_count == 3
        mock_set_cred.assert_any_call("PLAID_CLIENT_ID", "abc123")
        mock_set_cred.assert_any_call("PLAID_SECRET", "def456")
        mock_set_cred.assert_any_call("PLAID_ENVIRONMENT", "sandbox")

    def test_plaid_empty_client_id(self):
        """Empty Client ID raises ValueError."""
        with pytest.raises(ValueError, match="Client ID is required"):
            validate_and_store(
                "Plaid", {"client_id": "", "secret": "def456", "environment": "sandbox"}
            )

    def test_plaid_empty_secret(self):
        """Empty Secret raises ValueError."""
        with pytest.raises(ValueError, match="Secret is required"):
            validate_and_store(
                "Plaid", {"client_id": "abc123", "secret": "", "environment": "sandbox"}
            )

    def test_plaid_invalid_environment(self):
        """Invalid environment value raises ValueError."""
        with pytest.raises(ValueError, match="Invalid environment"):
            validate_and_store(
                "Plaid",
                {"client_id": "abc123", "secret": "def456", "environment": "development"},
            )

    @patch("plaid.api.plaid_api.PlaidApi.link_token_create")
    def test_plaid_invalid_credentials(self, mock_link_create):
        """API error raises ValueError with actionable message."""
        mock_link_create.side_effect = Exception("Connection failed")

        with pytest.raises(ValueError, match="Failed to validate Plaid credentials"):
            validate_and_store(
                "Plaid",
                {"client_id": "bad", "secret": "bad", "environment": "sandbox"},
            )

    @patch("plaid.api.plaid_api.PlaidApi.link_token_create")
    def test_plaid_invalid_api_keys_env_hint(self, mock_link_create):
        """INVALID_API_KEYS error suggests environment mismatch."""
        mock_link_create.side_effect = Exception(
            "INVALID_API_KEYS: the client_id or secret is invalid"
        )

        with pytest.raises(ValueError, match="environment matches your keys"):
            validate_and_store(
                "Plaid",
                {"client_id": "abc123", "secret": "def456", "environment": "sandbox"},
            )

    @patch("services.provider_setup.base.set_credential", return_value=False)
    @patch("plaid.api.plaid_api.PlaidApi.link_token_create")
    def test_plaid_keychain_failure(self, mock_link_create, mock_set_cred):
        """Keychain storage failure raises RuntimeError."""
        mock_link_create.return_value = {"link_token": "link-sandbox-test"}

        with pytest.raises(RuntimeError, match="Failed to store"):
            validate_and_store(
                "Plaid",
                {"client_id": "abc123", "secret": "def456", "environment": "sandbox"},
            )

    @patch.dict("sys.modules", {"plaid": None})
    def test_plaid_library_not_installed(self):
        """Missing plaid library raises RuntimeError with helpful message."""
        with pytest.raises(RuntimeError, match="Plaid library is not installed"):
            validate_and_store(
                "Plaid",
                {"client_id": "abc123", "secret": "def456", "environment": "sandbox"},
            )


class TestRemoveCredentials:
    """Tests for remove_credentials()."""

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_removes_simplefin_keys(self, mock_delete):
        """Removes SIMPLEFIN_ACCESS_URL from keychain."""
        result = remove_credentials("SimpleFIN")

        mock_delete.assert_called_once_with("SIMPLEFIN_ACCESS_URL")
        assert "removed" in result.lower()

    @patch("services.provider_setup.registry.delete_credential", return_value=False)
    def test_handles_delete_failure_gracefully(self, mock_delete):
        """Returns 'no credentials' message when key not found in Keychain."""
        result = remove_credentials("SimpleFIN")
        assert "no credentials" in result.lower()

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_removes_ibkr_keys(self, mock_delete):
        """Removes IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID from keychain."""
        result = remove_credentials("IBKR")

        assert mock_delete.call_count == 2
        mock_delete.assert_any_call("IBKR_FLEX_TOKEN")
        mock_delete.assert_any_call("IBKR_FLEX_QUERY_ID")
        assert "removed" in result.lower()

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_removes_coinbase_keys(self, mock_delete):
        """Removes COINBASE_API_KEY and COINBASE_API_SECRET from keychain."""
        result = remove_credentials("Coinbase")

        assert mock_delete.call_count == 2
        mock_delete.assert_any_call("COINBASE_API_KEY")
        mock_delete.assert_any_call("COINBASE_API_SECRET")
        assert "removed" in result.lower()

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_removes_plaid_keys(self, mock_delete):
        """Removes PLAID_CLIENT_ID, PLAID_SECRET, and PLAID_ENVIRONMENT from keychain."""
        result = remove_credentials("Plaid")

        assert mock_delete.call_count == 3
        mock_delete.assert_any_call("PLAID_CLIENT_ID")
        mock_delete.assert_any_call("PLAID_SECRET")
        mock_delete.assert_any_call("PLAID_ENVIRONMENT")
        assert "removed" in result.lower()

    def test_unknown_provider_raises(self):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="No setup configuration"):
            remove_credentials("UnknownProvider")


class TestSettingsSync:
    """Tests that validate_and_store / remove_credentials sync the settings singleton."""

    @patch("services.provider_setup.simplefin_setup.set_credential", return_value=True)
    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_setup_updates_settings(self, mock_get_url, mock_set_cred):
        """SimpleFIN setup updates settings.simplefin_access_url in memory."""
        from config import settings

        original = settings.SIMPLEFIN_ACCESS_URL
        mock_get_url.return_value = "https://bridge.simplefin.org/access/new123"

        try:
            validate_and_store("SimpleFIN", {"setup_token": "dGVzdA=="})
            assert settings.SIMPLEFIN_ACCESS_URL == "https://bridge.simplefin.org/access/new123"
        finally:
            settings.SIMPLEFIN_ACCESS_URL = original

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("scripts.setup_ibkr.validate_trade_columns", return_value=([], []))
    @patch("scripts.setup_ibkr.validate_query_sections", return_value=[])
    @patch("ibflex.client.download", return_value=b"<xml>report</xml>")
    def test_ibkr_setup_updates_settings(
        self, mock_download, mock_sections, mock_columns, mock_set_cred
    ):
        """IBKR setup updates settings.ibkr_flex_token and ibkr_flex_query_id."""
        from config import settings

        orig_token = settings.IBKR_FLEX_TOKEN
        orig_qid = settings.IBKR_FLEX_QUERY_ID

        try:
            validate_and_store(
                "IBKR", {"flex_token": "newtok", "flex_query_id": "789"}
            )
            assert settings.IBKR_FLEX_TOKEN == "newtok"
            assert settings.IBKR_FLEX_QUERY_ID == "789"
        finally:
            settings.IBKR_FLEX_TOKEN = orig_token
            settings.IBKR_FLEX_QUERY_ID = orig_qid

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("coinbase.rest.RESTClient")
    def test_coinbase_setup_updates_settings(self, mock_rest_cls, mock_set_cred):
        """Coinbase setup updates settings.COINBASE_API_KEY and COINBASE_API_SECRET."""
        from config import settings

        mock_client = MagicMock()
        mock_rest_cls.return_value = mock_client

        orig_key = settings.COINBASE_API_KEY
        orig_secret = settings.COINBASE_API_SECRET

        try:
            validate_and_store(
                "Coinbase",
                {"api_key": "newkey", "api_secret": "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----"},
            )
            assert settings.COINBASE_API_KEY == "newkey"
            assert settings.COINBASE_API_SECRET == "-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----"
        finally:
            settings.COINBASE_API_KEY = orig_key
            settings.COINBASE_API_SECRET = orig_secret

    @patch("services.provider_setup.base.set_credential", return_value=True)
    @patch("plaid.api.plaid_api.PlaidApi.link_token_create")
    def test_plaid_setup_updates_settings(self, mock_link_create, mock_set_cred):
        """Plaid setup updates settings for all three keys."""
        from config import settings

        mock_link_create.return_value = {"link_token": "link-sandbox-test"}

        orig_client_id = settings.PLAID_CLIENT_ID
        orig_secret = settings.PLAID_SECRET
        orig_env = settings.PLAID_ENVIRONMENT

        try:
            validate_and_store(
                "Plaid",
                {"client_id": "newclient", "secret": "newsecret", "environment": "production"},
            )
            assert settings.PLAID_CLIENT_ID == "newclient"
            assert settings.PLAID_SECRET == "newsecret"
            assert settings.PLAID_ENVIRONMENT == "production"
        finally:
            settings.PLAID_CLIENT_ID = orig_client_id
            settings.PLAID_SECRET = orig_secret
            settings.PLAID_ENVIRONMENT = orig_env

    @patch("services.provider_setup.registry.delete_credential", return_value=True)
    def test_remove_credentials_clears_settings(self, mock_delete):
        """Removing credentials clears the settings singleton values."""
        from config import settings

        orig_token = settings.IBKR_FLEX_TOKEN
        orig_qid = settings.IBKR_FLEX_QUERY_ID
        settings.IBKR_FLEX_TOKEN = "old_token"
        settings.IBKR_FLEX_QUERY_ID = "old_qid"

        try:
            remove_credentials("IBKR")
            assert settings.IBKR_FLEX_TOKEN == ""
            assert settings.IBKR_FLEX_QUERY_ID == ""
        finally:
            settings.IBKR_FLEX_TOKEN = orig_token
            settings.IBKR_FLEX_QUERY_ID = orig_qid
