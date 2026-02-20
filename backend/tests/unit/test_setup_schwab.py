"""Tests for the Charles Schwab setup and token refresh scripts."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.setup_schwab import (
    get_default_token_path,
    run_oauth_flow,
    validate_client,
)


class TestGetDefaultTokenPath:
    """Tests for get_default_token_path."""

    def test_returns_path_in_backend_dir(self):
        """Path ends with .schwab_token.json in the backend directory."""
        path = get_default_token_path()
        assert path.endswith(".schwab_token.json")
        # Should be in the backend directory (parent of scripts/)
        assert Path(path).parent.name == "backend" or "backend" in path


class TestRunOauthFlow:
    """Tests for run_oauth_flow."""

    @patch("scripts.setup_schwab.client_from_manual_flow")
    def test_success(self, mock_auth):
        """Calls client_from_manual_flow with correct args and returns client."""
        mock_client = MagicMock()
        mock_auth.return_value = mock_client

        result = run_oauth_flow(
            app_key="my-key",
            app_secret="my-secret",
            callback_url="https://127.0.0.1",
            token_path="/tmp/token.json",
        )

        mock_auth.assert_called_once_with(
            api_key="my-key",
            app_secret="my-secret",
            callback_url="https://127.0.0.1",
            token_path="/tmp/token.json",
        )
        assert result is mock_client

    @patch("scripts.setup_schwab.client_from_manual_flow")
    def test_oauth_failure_propagates(self, mock_auth):
        """OAuth failure propagates exception."""
        mock_auth.side_effect = Exception("OAuth error")

        with pytest.raises(Exception, match="OAuth error"):
            run_oauth_flow("key", "secret", "https://cb", "/tmp/token.json")


class TestValidateClient:
    """Tests for validate_client."""

    def test_success(self):
        """200 response returns parsed JSON list."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"accountNumber": "123", "hashValue": "abc"},
            {"accountNumber": "456", "hashValue": "def"},
        ]
        mock_client.get_account_numbers.return_value = mock_resp

        result = validate_client(mock_client)

        assert len(result) == 2
        assert result[0]["accountNumber"] == "123"
        mock_client.get_account_numbers.assert_called_once()

    def test_non_200_raises(self):
        """Non-200 status raises exception."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_client.get_account_numbers.return_value = mock_resp

        with pytest.raises(Exception, match="status 401"):
            validate_client(mock_client)

    def test_api_error_propagates(self):
        """API error propagates exception."""
        mock_client = MagicMock()
        mock_client.get_account_numbers.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            validate_client(mock_client)


class TestMainFlow:
    """Tests for the setup_schwab main() interactive flow."""

    @patch("scripts.setup_schwab.validate_client")
    @patch("scripts.setup_schwab.run_oauth_flow")
    @patch("scripts.setup_schwab._get_setting", return_value="")
    @patch("builtins.input")
    def test_successful_flow(
        self, mock_input, _mock_get, mock_oauth, mock_validate, capsys
    ):
        """Successful flow prints all env vars and 7-day warning."""
        mock_input.side_effect = [
            "my-app-key",
            "my-app-secret",
            "",  # default callback URL
            "",  # default token path
            "n",  # decline keychain storage
        ]
        mock_client = MagicMock()
        mock_oauth.return_value = mock_client
        mock_validate.return_value = [
            {"accountNumber": "12345", "hashValue": "abc"},
        ]

        from scripts.setup_schwab import main

        main()

        captured = capsys.readouterr()
        assert "SCHWAB_APP_KEY=my-app-key" in captured.out
        assert "SCHWAB_APP_SECRET=my-app-secret" in captured.out
        assert "SCHWAB_TOKEN_PATH=" in captured.out
        assert "7 days" in captured.out
        assert "Account 12345" in captured.out

    @patch("scripts.setup_schwab._get_setting", return_value="")
    @patch("builtins.input")
    def test_empty_app_key_exits(self, mock_input, _mock_get):
        """Empty App Key exits with code 1."""
        mock_input.side_effect = [""]

        from scripts.setup_schwab import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("scripts.setup_schwab._get_setting", return_value="")
    @patch("builtins.input")
    def test_empty_app_secret_exits(self, mock_input, _mock_get):
        """Empty App Secret exits with code 1."""
        mock_input.side_effect = ["my-key", ""]

        from scripts.setup_schwab import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("scripts.setup_schwab.validate_client")
    @patch("scripts.setup_schwab.run_oauth_flow")
    @patch("scripts.setup_schwab._get_setting", return_value="")
    @patch("builtins.input")
    def test_default_callback_url_used(
        self, mock_input, _mock_get, mock_oauth, mock_validate, capsys
    ):
        """Empty callback input uses default URL."""
        mock_input.side_effect = ["key", "secret", "", "", "n"]
        mock_oauth.return_value = MagicMock()
        mock_validate.return_value = []

        from scripts.setup_schwab import main

        main()

        mock_oauth.assert_called_once()
        args, kwargs = mock_oauth.call_args
        # callback_url is the 3rd positional arg
        assert args[2] == "https://127.0.0.1"

    @patch("scripts.setup_schwab.validate_client")
    @patch("scripts.setup_schwab.run_oauth_flow")
    @patch("scripts.setup_schwab._get_setting", return_value="")
    @patch("builtins.input")
    def test_default_token_path_used(
        self, mock_input, _mock_get, mock_oauth, mock_validate, capsys
    ):
        """Empty token path input uses default path."""
        mock_input.side_effect = ["key", "secret", "", "", "n"]
        mock_oauth.return_value = MagicMock()
        mock_validate.return_value = []

        from scripts.setup_schwab import main

        main()

        mock_oauth.assert_called_once()
        args, kwargs = mock_oauth.call_args
        # token_path is the 4th positional arg
        assert args[3].endswith(".schwab_token.json")

    @patch("scripts.setup_schwab.validate_client")
    @patch("scripts.setup_schwab.run_oauth_flow")
    @patch("scripts.setup_schwab._get_setting", return_value="")
    @patch("builtins.input")
    def test_non_default_callback_included_in_output(
        self, mock_input, _mock_get, mock_oauth, mock_validate, capsys
    ):
        """Non-default callback URL is included in env output."""
        mock_input.side_effect = [
            "key",
            "secret",
            "https://custom:9999",
            "",
            "n",  # decline keychain storage
        ]
        mock_oauth.return_value = MagicMock()
        mock_validate.return_value = []

        from scripts.setup_schwab import main

        main()

        captured = capsys.readouterr()
        assert "SCHWAB_CALLBACK_URL=https://custom:9999" in captured.out

    @patch("scripts.setup_schwab.validate_client")
    @patch("scripts.setup_schwab.run_oauth_flow")
    @patch("scripts.setup_schwab._get_setting", return_value="")
    @patch("builtins.input")
    def test_default_callback_omitted_from_output(
        self, mock_input, _mock_get, mock_oauth, mock_validate, capsys
    ):
        """Default callback URL is omitted from env output."""
        mock_input.side_effect = ["key", "secret", "", "", "n"]
        mock_oauth.return_value = MagicMock()
        mock_validate.return_value = []

        from scripts.setup_schwab import main

        main()

        captured = capsys.readouterr()
        assert "SCHWAB_CALLBACK_URL" not in captured.out

    @patch("scripts.setup_schwab._get_setting", return_value="")
    @patch("scripts.setup_schwab.run_oauth_flow")
    @patch("builtins.input")
    def test_oauth_failure_prints_common_issues(
        self, mock_input, mock_oauth, _mock_get, capsys
    ):
        """OAuth failure prints error and common issues."""
        mock_input.side_effect = ["key", "secret", "", ""]
        mock_oauth.side_effect = Exception("OAuth failed")

        from scripts.setup_schwab import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "OAuth failed" in captured.out
        assert "Common issues:" in captured.out

    @patch("scripts.setup_schwab.validate_client")
    @patch("scripts.setup_schwab.run_oauth_flow")
    @patch("builtins.input")
    def test_uses_stored_credentials_when_accepted(
        self, mock_input, mock_oauth, mock_validate, capsys
    ):
        """Accepting stored credentials skips manual entry."""
        mock_input.side_effect = [
            "y",   # use stored credentials
            "",    # default callback URL
            "",    # default token path
            "n",   # decline keychain storage
        ]
        mock_oauth.return_value = MagicMock()
        mock_validate.return_value = [
            {"accountNumber": "99999", "hashValue": "xyz"},
        ]

        stored = {
            "SCHWAB_APP_KEY": "stored-key",
            "SCHWAB_APP_SECRET": "stored-secret",
            "SCHWAB_CALLBACK_URL": "",
            "SCHWAB_TOKEN_PATH": "",
        }
        with patch("scripts.setup_schwab._get_setting", side_effect=lambda k: stored.get(k, "")):
            from scripts.setup_schwab import main

            main()

        captured = capsys.readouterr()
        assert "Found stored credentials" in captured.out
        assert "SCHWAB_APP_KEY=stored-key" in captured.out
        assert "SCHWAB_APP_SECRET=stored-secret" in captured.out
        # Verify the stored key was passed to the OAuth flow
        args, _ = mock_oauth.call_args
        assert args[0] == "stored-key"
        assert args[1] == "stored-secret"

    @patch("scripts.setup_schwab.validate_client")
    @patch("scripts.setup_schwab.run_oauth_flow")
    @patch("builtins.input")
    def test_declining_stored_credentials_prompts_manual(
        self, mock_input, mock_oauth, mock_validate, capsys
    ):
        """Declining stored credentials falls back to manual entry."""
        mock_input.side_effect = [
            "n",           # decline stored credentials
            "new-key",     # manual App Key
            "new-secret",  # manual App Secret
            "",            # default callback URL
            "",            # default token path
            "n",           # decline keychain storage
        ]
        mock_oauth.return_value = MagicMock()
        mock_validate.return_value = []

        stored = {
            "SCHWAB_APP_KEY": "stored-key",
            "SCHWAB_APP_SECRET": "stored-secret",
            "SCHWAB_CALLBACK_URL": "",
            "SCHWAB_TOKEN_PATH": "",
        }
        with patch("scripts.setup_schwab._get_setting", side_effect=lambda k: stored.get(k, "")):
            from scripts.setup_schwab import main

            main()

        captured = capsys.readouterr()
        assert "SCHWAB_APP_KEY=new-key" in captured.out
        assert "SCHWAB_APP_SECRET=new-secret" in captured.out


class TestRefreshMainFlow:
    """Tests for the refresh_schwab_token main() flow."""

    @patch("scripts.refresh_schwab_token.validate_client")
    @patch("scripts.refresh_schwab_token.run_oauth_flow")
    @patch("scripts.refresh_schwab_token.settings")
    def test_successful_refresh(self, mock_settings, mock_oauth, mock_validate, capsys):
        """Successful refresh prints success and account count."""
        mock_settings.SCHWAB_APP_KEY = "my-key"
        mock_settings.SCHWAB_APP_SECRET = "my-secret"
        mock_settings.SCHWAB_CALLBACK_URL = "https://127.0.0.1"
        mock_settings.SCHWAB_TOKEN_PATH = "/tmp/token.json"

        mock_client = MagicMock()
        mock_oauth.return_value = mock_client
        mock_validate.return_value = [
            {"accountNumber": "111", "hashValue": "aaa"},
            {"accountNumber": "222", "hashValue": "bbb"},
        ]

        from scripts.refresh_schwab_token import main

        main()

        captured = capsys.readouterr()
        assert "2 account(s)" in captured.out
        assert "Success" in captured.out
        assert "/tmp/token.json" in captured.out

    @patch("scripts.refresh_schwab_token.settings")
    def test_missing_credentials_exits(self, mock_settings):
        """Missing SCHWAB_APP_KEY exits with code 1."""
        mock_settings.SCHWAB_APP_KEY = ""
        mock_settings.SCHWAB_APP_SECRET = ""

        from scripts.refresh_schwab_token import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("scripts.refresh_schwab_token.run_oauth_flow")
    @patch("scripts.refresh_schwab_token.settings")
    def test_oauth_failure_prints_error(
        self, mock_settings, mock_oauth, capsys
    ):
        """OAuth failure prints error info."""
        mock_settings.SCHWAB_APP_KEY = "my-key"
        mock_settings.SCHWAB_APP_SECRET = "my-secret"
        mock_settings.SCHWAB_CALLBACK_URL = "https://127.0.0.1"
        mock_settings.SCHWAB_TOKEN_PATH = "/tmp/token.json"

        mock_oauth.side_effect = Exception("Token expired")

        from scripts.refresh_schwab_token import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Token expired" in captured.out
        assert "Common issues:" in captured.out
