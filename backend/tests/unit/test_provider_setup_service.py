"""Unit tests for the provider setup service."""

from unittest.mock import patch

import pytest

from services.provider_setup_service import (
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

    def test_unknown_provider_raises(self):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="No setup configuration"):
            get_setup_fields("UnknownProvider")

    def test_provider_without_setup_raises(self):
        """Known provider without setup config raises ValueError."""
        # SnapTrade is a known provider but has no setup entry
        with pytest.raises(ValueError, match="No setup configuration"):
            get_setup_fields("SnapTrade")


class TestValidateAndStore:
    """Tests for validate_and_store()."""

    @patch("services.provider_setup_service.set_credential", return_value=True)
    @patch("simplefin.SimpleFINClient.get_access_url")
    def test_simplefin_success(self, mock_get_url, mock_set_cred):
        """Successful SimpleFIN setup exchanges token and stores access URL."""
        mock_get_url.return_value = "https://bridge.simplefin.org/access/abc123"

        result = validate_and_store("SimpleFIN", {"setup_token": "dGVzdA=="})

        mock_get_url.assert_called_once_with("dGVzdA==")
        mock_set_cred.assert_called_once_with(
            "SIMPLEFIN_ACCESS_URL", "https://bridge.simplefin.org/access/abc123"
        )
        assert "successfully" in result.lower()

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

    @patch("services.provider_setup_service.set_credential", return_value=False)
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
        "services.provider_setup_service.PROVIDER_CREDENTIAL_MAP",
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


class TestRemoveCredentials:
    """Tests for remove_credentials()."""

    @patch("services.provider_setup_service.delete_credential", return_value=True)
    def test_removes_simplefin_keys(self, mock_delete):
        """Removes SIMPLEFIN_ACCESS_URL from keychain."""
        result = remove_credentials("SimpleFIN")

        mock_delete.assert_called_once_with("SIMPLEFIN_ACCESS_URL")
        assert "removed" in result.lower()

    @patch("services.provider_setup_service.delete_credential", return_value=False)
    def test_handles_delete_failure_gracefully(self, mock_delete):
        """Returns 'no credentials' message when key not found in Keychain."""
        result = remove_credentials("SimpleFIN")
        assert "no credentials" in result.lower()

    def test_unknown_provider_raises(self):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="No setup configuration"):
            remove_credentials("UnknownProvider")
