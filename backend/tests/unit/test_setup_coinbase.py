"""Tests for the Coinbase Advanced Trade API setup script."""

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.setup_coinbase import (
    format_secret_for_env,
    validate_with_api_key,
    validate_with_key_file,
)


SAMPLE_PEM = (
    "-----BEGIN EC PRIVATE KEY-----\n"
    "MHQCAQEEIBkg4LVWM9nuwNSk3yByxZpYRTBnVJk3GOAPYI/RSGX8oAcGBSuBBAAi\n"
    "oWQDYgAE+Y+qPqxhlVOYsw==\n"
    "-----END EC PRIVATE KEY-----\n"
)

SAMPLE_KEY_FILE_WITH_NAME = {
    "name": "organizations/abc-123/apiKeys/key-456",
    "privateKey": SAMPLE_PEM,
}

SAMPLE_KEY_FILE_WITH_ID = {
    "id": "organizations/abc-123/apiKeys/key-456",
    "privateKey": SAMPLE_PEM,
}


class TestValidateWithKeyFile:
    """Tests for the validate_with_key_file function."""

    @patch("scripts.setup_coinbase.RESTClient")
    def test_success_with_name_field(self, mock_client_cls, tmp_path):
        """Key file with 'name' field creates client and returns credentials."""
        key_file = tmp_path / "cdp_api_key.json"
        key_file.write_text(json.dumps(SAMPLE_KEY_FILE_WITH_NAME))

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        result = validate_with_key_file(str(key_file))

        mock_client_cls.assert_called_once_with(
            api_key="organizations/abc-123/apiKeys/key-456",
            api_secret=SAMPLE_PEM,
        )
        mock_client.get_accounts.assert_called_once_with(limit=1)
        assert result["api_key"] == "organizations/abc-123/apiKeys/key-456"
        assert result["api_secret"] == SAMPLE_PEM

    @patch("scripts.setup_coinbase.RESTClient")
    def test_success_with_id_field(self, mock_client_cls, tmp_path):
        """Key file with 'id' field (no 'name') creates client and returns credentials."""
        key_file = tmp_path / "cdp_api_key.json"
        key_file.write_text(json.dumps(SAMPLE_KEY_FILE_WITH_ID))

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        result = validate_with_key_file(str(key_file))

        mock_client_cls.assert_called_once_with(
            api_key="organizations/abc-123/apiKeys/key-456",
            api_secret=SAMPLE_PEM,
        )
        mock_client.get_accounts.assert_called_once_with(limit=1)
        assert result["api_key"] == "organizations/abc-123/apiKeys/key-456"
        assert result["api_secret"] == SAMPLE_PEM

    @patch("scripts.setup_coinbase.RESTClient")
    def test_name_field_preferred_over_id(self, mock_client_cls, tmp_path):
        """When both 'name' and 'id' are present, 'name' is used."""
        data = {
            "name": "organizations/abc/apiKeys/from-name",
            "id": "organizations/abc/apiKeys/from-id",
            "privateKey": SAMPLE_PEM,
        }
        key_file = tmp_path / "cdp_api_key.json"
        key_file.write_text(json.dumps(data))

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        result = validate_with_key_file(str(key_file))

        assert result["api_key"] == "organizations/abc/apiKeys/from-name"

    def test_file_not_found(self):
        """Non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            validate_with_key_file("/nonexistent/path/key.json")

    def test_invalid_json(self, tmp_path):
        """Invalid JSON raises ValueError."""
        key_file = tmp_path / "bad.json"
        key_file.write_text("not json {{{")

        with pytest.raises(ValueError, match="Invalid JSON"):
            validate_with_key_file(str(key_file))

    def test_missing_name_and_id_fields(self, tmp_path):
        """Key file without 'name' or 'id' raises ValueError."""
        key_file = tmp_path / "no_name.json"
        key_file.write_text(json.dumps({"privateKey": SAMPLE_PEM}))

        with pytest.raises(ValueError, match="missing required field"):
            validate_with_key_file(str(key_file))

    def test_missing_private_key_field(self, tmp_path):
        """Key file without 'privateKey' raises ValueError."""
        key_file = tmp_path / "no_key.json"
        key_file.write_text(json.dumps({"name": "organizations/abc/apiKeys/key"}))

        with pytest.raises(ValueError, match="missing required field: 'privateKey'"):
            validate_with_key_file(str(key_file))

    @patch("scripts.setup_coinbase.RESTClient")
    def test_api_failure(self, mock_client_cls, tmp_path):
        """API call failure propagates the exception."""
        key_file = tmp_path / "cdp_api_key.json"
        key_file.write_text(json.dumps(SAMPLE_KEY_FILE_WITH_NAME))

        mock_client = MagicMock()
        mock_client.get_accounts.side_effect = Exception("Unauthorized")
        mock_client_cls.return_value = mock_client

        with pytest.raises(Exception, match="Unauthorized"):
            validate_with_key_file(str(key_file))


class TestValidateWithApiKey:
    """Tests for the validate_with_api_key function."""

    @patch("scripts.setup_coinbase.RESTClient")
    def test_success(self, mock_client_cls):
        """Valid credentials create client and call get_accounts."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        validate_with_api_key("org/abc/apiKeys/key-1", SAMPLE_PEM)

        mock_client_cls.assert_called_once_with(
            api_key="org/abc/apiKeys/key-1", api_secret=SAMPLE_PEM
        )
        mock_client.get_accounts.assert_called_once_with(limit=1)

    @patch("scripts.setup_coinbase.RESTClient")
    def test_api_failure(self, mock_client_cls):
        """API call failure propagates the exception."""
        mock_client = MagicMock()
        mock_client.get_accounts.side_effect = Exception("Invalid API key")
        mock_client_cls.return_value = mock_client

        with pytest.raises(Exception, match="Invalid API key"):
            validate_with_api_key("bad-key", "bad-secret")


class TestFormatSecretForEnv:
    """Tests for the format_secret_for_env function."""

    def test_newlines_escaped(self):
        """Real newlines are escaped to literal \\n."""
        result = format_secret_for_env("line1\nline2\nline3")
        assert result == "line1\\nline2\\nline3"

    def test_no_newlines_unchanged(self):
        """String without newlines is returned unchanged."""
        result = format_secret_for_env("no-newlines-here")
        assert result == "no-newlines-here"

    def test_pem_key_escaped(self):
        """Full PEM key has all newlines escaped."""
        result = format_secret_for_env(SAMPLE_PEM)
        assert "\n" not in result
        assert "\\n" in result
        assert result.startswith("-----BEGIN EC PRIVATE KEY-----")

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert format_secret_for_env("") == ""


class TestNormalizePemNewlines:
    """Tests for the Settings.normalize_pem_newlines validator."""

    def test_literal_backslash_n_converted(self):
        """Literal \\n sequences are converted to real newlines."""
        from config import Settings

        result = Settings.normalize_pem_newlines("line1\\nline2\\nline3")
        assert result == "line1\nline2\nline3"

    def test_real_newlines_preserved(self):
        """Strings with only real newlines are unchanged."""
        from config import Settings

        result = Settings.normalize_pem_newlines("line1\nline2\nline3")
        assert result == "line1\nline2\nline3"

    def test_empty_string_unchanged(self):
        """Empty string returns empty string."""
        from config import Settings

        result = Settings.normalize_pem_newlines("")
        assert result == ""

    def test_no_newlines_unchanged(self):
        """String without any newlines is returned unchanged."""
        from config import Settings

        result = Settings.normalize_pem_newlines("simple-string")
        assert result == "simple-string"


class TestMainFlow:
    """Tests for the main() interactive flow."""

    @patch("scripts.setup_coinbase.validate_with_key_file")
    @patch("builtins.input")
    def test_method_1_success(self, mock_input, mock_validate, capsys):
        """Method 1 success prints COINBASE_KEY_FILE and inline alternative."""
        mock_input.side_effect = ["1", "/path/to/key.json", "n"]
        mock_validate.return_value = {
            "api_key": "organizations/abc/apiKeys/key-1",
            "api_secret": "-----BEGIN EC PRIVATE KEY-----\ndata\n-----END EC PRIVATE KEY-----\n",
        }

        from scripts.setup_coinbase import main

        main()

        captured = capsys.readouterr()
        assert "COINBASE_KEY_FILE=" in captured.out
        assert "COINBASE_API_KEY=organizations/abc/apiKeys/key-1" in captured.out
        assert "COINBASE_API_SECRET=" in captured.out

    @patch("scripts.setup_coinbase.validate_with_api_key")
    @patch("builtins.input")
    def test_method_2_success(self, mock_input, mock_validate, capsys):
        """Method 2 success prints COINBASE_API_KEY and double-quoted secret."""
        mock_input.side_effect = [
            "2",
            "organizations/abc/apiKeys/key-1",
            "-----BEGIN EC PRIVATE KEY-----",
            "MHQCAQEEIBkg4LVWM9nuwNSk3yByxZpY",
            "-----END EC PRIVATE KEY-----",
            "",  # First empty line to end PEM
            "",  # Second empty line to trigger double-Enter
            "n",  # decline keychain storage
        ]

        from scripts.setup_coinbase import main

        main()

        captured = capsys.readouterr()
        assert "COINBASE_API_KEY=organizations/abc/apiKeys/key-1" in captured.out
        assert 'COINBASE_API_SECRET="' in captured.out
        mock_validate.assert_called_once()

    @patch("builtins.input")
    def test_empty_file_path_exits(self, mock_input):
        """Empty file path in method 1 exits with code 1."""
        mock_input.side_effect = ["1", ""]

        from scripts.setup_coinbase import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("builtins.input")
    def test_empty_api_key_exits(self, mock_input):
        """Empty API key in method 2 exits with code 1."""
        mock_input.side_effect = ["2", ""]

        from scripts.setup_coinbase import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("builtins.input")
    def test_empty_api_secret_exits(self, mock_input):
        """Empty API secret in method 2 exits with code 1."""
        mock_input.side_effect = ["2", "some-key", "", ""]

        from scripts.setup_coinbase import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("builtins.input")
    def test_invalid_method_exits(self, mock_input):
        """Invalid method choice exits with code 1."""
        mock_input.side_effect = ["3"]

        from scripts.setup_coinbase import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("scripts.setup_coinbase.validate_with_key_file")
    @patch("builtins.input")
    def test_method_1_validation_failure(self, mock_input, mock_validate, capsys):
        """Method 1 validation failure prints error and common issues."""
        mock_input.side_effect = ["1", "/path/to/key.json"]
        mock_validate.side_effect = Exception("Unauthorized")

        from scripts.setup_coinbase import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Unauthorized" in captured.out
        assert "Common issues:" in captured.out

    @patch("scripts.setup_coinbase.validate_with_api_key")
    @patch("builtins.input")
    def test_method_2_validation_failure(self, mock_input, mock_validate, capsys):
        """Method 2 validation failure prints error and common issues."""
        mock_input.side_effect = [
            "2",
            "bad-key",
            "bad-secret",
            "",
            "",
        ]
        mock_validate.side_effect = Exception("Invalid API key")

        from scripts.setup_coinbase import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Invalid API key" in captured.out
        assert "Common issues:" in captured.out

    @patch("scripts.setup_coinbase.validate_with_key_file")
    @patch("builtins.input")
    def test_ecdsa_hint_in_error_output(self, mock_input, mock_validate, capsys):
        """Validation failure mentions Ed25519 vs ECDSA in troubleshooting."""
        mock_input.side_effect = ["1", "/path/to/key.json"]
        mock_validate.side_effect = Exception("Could not deserialize key data")

        from scripts.setup_coinbase import main

        with pytest.raises(SystemExit):
            main()

        captured = capsys.readouterr()
        assert "Ed25519" in captured.out
        assert "ECDSA" in captured.out
