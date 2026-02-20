"""Tests for the SnapTrade setup script."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.setup_snaptrade import (
    _get_attr,
    disconnect_authorization,
    list_connections,
    reset_user_secret,
)


# -- Sample data fixtures --

AUTHORIZATION_1 = {
    "id": "auth-111-aaa",
    "name": "Connection-1",
    "type": "Active",
    "brokerage": {"name": "Robinhood"},
}

AUTHORIZATION_2 = {
    "id": "auth-222-bbb",
    "name": "Connection-2",
    "type": "Active",
    "brokerage": {"name": "Wealthsimple"},
}

ACCOUNT_1 = {
    "id": "acct-001",
    "name": "Individual Brokerage",
    "brokerage_authorization": "auth-111-aaa",
}

ACCOUNT_2 = {
    "id": "acct-002",
    "name": "Roth IRA",
    "brokerage_authorization": "auth-111-aaa",
}

ACCOUNT_3 = {
    "id": "acct-003",
    "name": "TFSA",
    "brokerage_authorization": "auth-222-bbb",
}

ENV_VARS = {
    "SNAPTRADE_CLIENT_ID": "test-client-id",
    "SNAPTRADE_CONSUMER_KEY": "test-consumer-key",
    "SNAPTRADE_USER_ID": "test-user",
    "SNAPTRADE_USER_SECRET": "test-secret",
}


def _make_mock_client(authorizations=None, accounts=None):
    """Create a mock SnapTrade client with connections and account_information."""
    client = MagicMock()
    client.connections.list_brokerage_authorizations.return_value = (
        authorizations if authorizations is not None else []
    )
    client.account_information.list_user_accounts.return_value = (
        accounts if accounts is not None else []
    )
    client.connections.remove_brokerage_authorization.return_value = None
    return client


class TestGetAttr:
    """Tests for the _get_attr helper."""

    def test_dict_returns_value(self):
        assert _get_attr({"name": "Foo"}, "name") == "Foo"

    def test_dict_returns_default(self):
        assert _get_attr({}, "name") == "Unknown"

    def test_dict_custom_default(self):
        assert _get_attr({}, "name", "N/A") == "N/A"

    def test_object_returns_value(self):
        obj = MagicMock()
        obj.name = "Bar"
        assert _get_attr(obj, "name") == "Bar"

    def test_object_returns_default(self):
        obj = MagicMock(spec=[])  # No attributes
        assert _get_attr(obj, "name") == "Unknown"


class TestListConnections:
    """Tests for the list_connections function."""

    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_lists_connections_with_grouped_accounts(
        self, _mock_dotenv, mock_get_client, capsys
    ):
        """Connections are displayed with their accounts grouped underneath."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1, AUTHORIZATION_2],
            accounts=[ACCOUNT_1, ACCOUNT_2, ACCOUNT_3],
        )
        mock_get_client.return_value = mock_client

        list_connections()

        output = capsys.readouterr().out
        assert "Found 2 connection(s):" in output
        assert "Connection-1 (Robinhood)" in output
        assert "Auth ID:    auth-111-aaa" in output
        assert "Individual Brokerage (ID: acct-001)" in output
        assert "Roth IRA (ID: acct-002)" in output
        assert "Connection-2 (Wealthsimple)" in output
        assert "Auth ID:    auth-222-bbb" in output
        assert "TFSA (ID: acct-003)" in output

    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_no_connections(self, _mock_dotenv, mock_get_client, capsys):
        """Empty connections list shows zero count."""
        mock_client = _make_mock_client(authorizations=[], accounts=[])
        mock_get_client.return_value = mock_client

        list_connections()

        output = capsys.readouterr().out
        assert "Found 0 connection(s):" in output

    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_connection_with_no_accounts(self, _mock_dotenv, mock_get_client, capsys):
        """Connection with no matching accounts shows '(none)'."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[],
        )
        mock_get_client.return_value = mock_client

        list_connections()

        output = capsys.readouterr().out
        assert "Connection-1 (Robinhood)" in output
        assert "Accounts:   (none)" in output

    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_orphaned_accounts_shown(self, _mock_dotenv, mock_get_client, capsys):
        """Accounts with no matching authorization appear in orphaned section."""
        orphaned_account = {
            "id": "acct-orphan",
            "name": "Orphan Account",
            "brokerage_authorization": None,
        }
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[ACCOUNT_1, orphaned_account],
        )
        mock_get_client.return_value = mock_client

        list_connections()

        output = capsys.readouterr().out
        assert "Accounts with no connection:" in output
        assert "Orphan Account (ID: acct-orphan)" in output

    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_shows_status(self, _mock_dotenv, mock_get_client, capsys):
        """Connection type/status is displayed."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[],
        )
        mock_get_client.return_value = mock_client

        list_connections()

        output = capsys.readouterr().out
        assert "Status:     Active" in output

    @patch("scripts.setup_snaptrade._get_setting", return_value="")
    @patch.dict("os.environ", {}, clear=True)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_missing_credentials_exits(self, _mock_dotenv, _mock_get_setting):
        """Missing SNAPTRADE_USER_ID/SECRET exits with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            list_connections()
        assert exc_info.value.code == 1

    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_api_error_exits(self, _mock_dotenv, mock_get_client):
        """API error during listing exits with code 1."""
        mock_client = MagicMock()
        mock_client.connections.list_brokerage_authorizations.side_effect = Exception(
            "API error"
        )
        mock_get_client.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            list_connections()
        assert exc_info.value.code == 1


class TestDisconnectAuthorization:
    """Tests for the disconnect_authorization function."""

    @patch("builtins.input", return_value="y")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_successful_disconnect(
        self, _mock_dotenv, mock_get_client, _mock_input, capsys
    ):
        """Confirming 'y' calls remove_brokerage_authorization and prints success."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[ACCOUNT_1, ACCOUNT_2],
        )
        mock_get_client.return_value = mock_client

        disconnect_authorization("auth-111-aaa")

        mock_client.connections.remove_brokerage_authorization.assert_called_once_with(
            authorization_id="auth-111-aaa",
            user_id="test-user",
            user_secret="test-secret",
        )
        output = capsys.readouterr().out
        assert "SUCCESS!" in output
        assert "Connection-1" in output

    @patch("builtins.input", return_value="y")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_shows_affected_accounts(
        self, _mock_dotenv, mock_get_client, _mock_input, capsys
    ):
        """Confirmation prompt shows accounts that will be removed."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[ACCOUNT_1, ACCOUNT_2],
        )
        mock_get_client.return_value = mock_client

        disconnect_authorization("auth-111-aaa")

        output = capsys.readouterr().out
        assert "Accounts that will be removed:" in output
        assert "Individual Brokerage (ID: acct-001)" in output
        assert "Roth IRA (ID: acct-002)" in output

    @patch("builtins.input", return_value="n")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_abort_on_decline(
        self, _mock_dotenv, mock_get_client, _mock_input, capsys
    ):
        """Declining with 'n' aborts without calling the API."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[ACCOUNT_1],
        )
        mock_get_client.return_value = mock_client

        disconnect_authorization("auth-111-aaa")

        mock_client.connections.remove_brokerage_authorization.assert_not_called()
        output = capsys.readouterr().out
        assert "Aborted." in output

    @patch("builtins.input", return_value="")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_empty_input_aborts(
        self, _mock_dotenv, mock_get_client, _mock_input, capsys
    ):
        """Empty input (just pressing Enter) aborts."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[],
        )
        mock_get_client.return_value = mock_client

        disconnect_authorization("auth-111-aaa")

        mock_client.connections.remove_brokerage_authorization.assert_not_called()
        output = capsys.readouterr().out
        assert "Aborted." in output

    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_unknown_authorization_id_exits(
        self, _mock_dotenv, mock_get_client, capsys
    ):
        """Non-existent authorization ID exits with code 1."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[],
        )
        mock_get_client.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            disconnect_authorization("nonexistent-id")
        assert exc_info.value.code == 1

        output = capsys.readouterr().out
        assert "No connection found" in output

    @patch("scripts.setup_snaptrade._get_setting", return_value="")
    @patch.dict("os.environ", {}, clear=True)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_missing_credentials_exits(self, _mock_dotenv, _mock_get_setting):
        """Missing SNAPTRADE_USER_ID/SECRET exits with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            disconnect_authorization("any-id")
        assert exc_info.value.code == 1

    @patch("builtins.input", return_value="y")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_api_error_on_remove_exits(
        self, _mock_dotenv, mock_get_client, _mock_input
    ):
        """API error during remove exits with code 1."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[],
        )
        mock_client.connections.remove_brokerage_authorization.side_effect = Exception(
            "API error"
        )
        mock_get_client.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            disconnect_authorization("auth-111-aaa")
        assert exc_info.value.code == 1

    @patch("builtins.input", return_value="y")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_connection_with_no_accounts_shows_none(
        self, _mock_dotenv, mock_get_client, _mock_input, capsys
    ):
        """Connection with no accounts shows '(none)' in confirmation."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1],
            accounts=[],
        )
        mock_get_client.return_value = mock_client

        disconnect_authorization("auth-111-aaa")

        output = capsys.readouterr().out
        assert "Accounts:   (none)" in output

    @patch("builtins.input", return_value="y")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_only_matching_accounts_shown(
        self, _mock_dotenv, mock_get_client, _mock_input, capsys
    ):
        """Only accounts belonging to the target connection are listed."""
        mock_client = _make_mock_client(
            authorizations=[AUTHORIZATION_1, AUTHORIZATION_2],
            accounts=[ACCOUNT_1, ACCOUNT_3],  # acct_1 -> auth_1, acct_3 -> auth_2
        )
        mock_get_client.return_value = mock_client

        disconnect_authorization("auth-111-aaa")

        output = capsys.readouterr().out
        assert "Individual Brokerage" in output
        assert "TFSA" not in output


class TestResetUserSecret:
    """Tests for the reset_user_secret function."""

    @patch("builtins.input", return_value="n")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_rotates_secret_successfully(
        self, _mock_dotenv, mock_get_client, _mock_input, capsys
    ):
        """Calls reset_snap_trade_user_secret and prints new secret."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.body = {"userSecret": "new-rotated-secret"}
        mock_client.authentication.reset_snap_trade_user_secret.return_value = (
            mock_response
        )
        mock_get_client.return_value = mock_client

        reset_user_secret("test-user")

        mock_client.authentication.reset_snap_trade_user_secret.assert_called_once_with(
            user_id="test-user",
            user_secret="test-secret",
        )
        output = capsys.readouterr().out
        assert "SUCCESS!" in output
        assert "SNAPTRADE_USER_SECRET=new-rotated-secret" in output
        assert "preserves all existing brokerage connections" in output

    @patch("scripts.setup_snaptrade._get_setting")
    @patch.dict("os.environ", {}, clear=True)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_missing_user_secret_exits(self, _mock_dotenv, mock_get_setting):
        """Missing SNAPTRADE_USER_SECRET exits with code 1."""
        mock_get_setting.side_effect = lambda key: (
            "test-client-id" if key == "SNAPTRADE_CLIENT_ID"
            else "test-consumer-key" if key == "SNAPTRADE_CONSUMER_KEY"
            else ""
        )

        with pytest.raises(SystemExit) as exc_info:
            reset_user_secret("test-user")
        assert exc_info.value.code == 1

    @patch("builtins.input", return_value="n")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_api_error_exits(self, _mock_dotenv, mock_get_client, _mock_input):
        """API error during rotation exits with code 1."""
        mock_client = MagicMock()
        mock_client.authentication.reset_snap_trade_user_secret.side_effect = (
            Exception("API error")
        )
        mock_get_client.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            reset_user_secret("test-user")
        assert exc_info.value.code == 1

    @patch("builtins.input", return_value="n")
    @patch("scripts.setup_snaptrade.get_client")
    @patch.dict("os.environ", ENV_VARS)
    @patch("scripts.setup_snaptrade.load_dotenv")
    def test_does_not_delete_user(
        self, _mock_dotenv, mock_get_client, _mock_input, capsys
    ):
        """Rotation does NOT call delete_snap_trade_user."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.body = {"userSecret": "new-secret"}
        mock_client.authentication.reset_snap_trade_user_secret.return_value = (
            mock_response
        )
        mock_get_client.return_value = mock_client

        reset_user_secret("test-user")

        mock_client.authentication.delete_snap_trade_user.assert_not_called()
        mock_client.authentication.register_snap_trade_user.assert_not_called()
