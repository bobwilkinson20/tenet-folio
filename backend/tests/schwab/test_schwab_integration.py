"""Integration tests for Charles Schwab Individual Trader API.

These tests run against the real Schwab API using test credentials.
The client is created once per session to minimize API calls.

Run with: pytest -m schwab
"""

from decimal import Decimal

import pytest

from integrations.provider_protocol import (
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncResult,
)


pytestmark = pytest.mark.schwab


class TestSchwabAccounts:
    """Tests for account fetching."""

    def test_get_accounts_returns_list(self, schwab_client):
        """Fetching accounts returns a non-empty list."""
        accounts = schwab_client.get_accounts()

        assert isinstance(accounts, list)
        assert len(accounts) > 0, "Expected at least one account"

    def test_account_has_required_fields(self, schwab_client):
        """Each account has all required fields populated."""
        accounts = schwab_client.get_accounts()
        account = accounts[0]

        assert isinstance(account, ProviderAccount)
        assert isinstance(account.id, str)
        assert len(account.id) > 0
        assert isinstance(account.name, str)
        assert len(account.name) > 0
        assert account.institution == "Charles Schwab"

    def test_account_number_present(self, schwab_client):
        """Accounts include an account_number."""
        accounts = schwab_client.get_accounts()
        account = accounts[0]

        assert account.account_number is not None
        assert len(account.account_number) > 0


class TestSchwabHoldings:
    """Tests for holdings (positions) fetching."""

    def test_get_holdings_returns_list(self, schwab_client):
        """Fetching holdings returns a list."""
        holdings = schwab_client.get_holdings()

        assert isinstance(holdings, list)

    def test_holding_has_required_fields(self, schwab_client):
        """Each holding has required fields with correct types."""
        holdings = schwab_client.get_holdings()

        if len(holdings) == 0:
            pytest.skip("No holdings in test account to verify")

        holding = holdings[0]
        assert isinstance(holding, ProviderHolding)
        assert isinstance(holding.symbol, str)
        assert len(holding.symbol) > 0
        assert isinstance(holding.quantity, Decimal)
        assert isinstance(holding.price, Decimal)
        assert isinstance(holding.market_value, Decimal)
        assert isinstance(holding.currency, str)
        assert len(holding.currency) > 0

    def test_holdings_reference_valid_accounts(self, schwab_client):
        """All holdings reference an account that exists."""
        accounts = schwab_client.get_accounts()
        account_ids = {a.id for a in accounts}

        holdings = schwab_client.get_holdings()

        for holding in holdings:
            assert holding.account_id in account_ids, (
                f"Holding references unknown account: {holding.account_id}"
            )

    def test_filter_by_account_id(self, schwab_client):
        """Holdings can be filtered by account_id."""
        accounts = schwab_client.get_accounts()
        if len(accounts) == 0:
            pytest.skip("No accounts available for filtering test")

        first_account_id = accounts[0].id
        holdings = schwab_client.get_holdings(account_id=first_account_id)

        for holding in holdings:
            assert holding.account_id == first_account_id


class TestSchwabActivities:
    """Tests for activity (transaction) fetching."""

    def test_get_activities_returns_list(self, schwab_client):
        """Fetching activities returns a list."""
        accounts = schwab_client.get_accounts()
        assert len(accounts) > 0

        activities = schwab_client.get_activities(account_id=accounts[0].id)
        assert isinstance(activities, list)

    def test_activity_has_required_fields(self, schwab_client):
        """Each activity has required fields populated."""
        accounts = schwab_client.get_accounts()
        activities = schwab_client.get_activities(account_id=accounts[0].id)

        if len(activities) == 0:
            pytest.skip("No activities in test account to verify")

        activity = activities[0]
        assert isinstance(activity, ProviderActivity)
        assert isinstance(activity.external_id, str)
        assert len(activity.external_id) > 0
        assert isinstance(activity.type, str)
        assert activity.activity_date is not None


class TestSchwabSyncAll:
    """Tests for sync_all() orchestration."""

    def test_sync_all_returns_complete_result(self, schwab_client):
        """sync_all returns accounts, holdings, and no errors."""
        result = schwab_client.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.accounts) > 0
        assert len(result.holdings) >= 0
        assert len(result.balance_dates) > 0
        assert result.errors == []

    def test_sync_all_activities_populated(self, schwab_client):
        """sync_all includes activities in the result."""
        result = schwab_client.sync_all()

        assert isinstance(result.activities, list)
        # Activities may be empty if the account has no recent transactions


class TestSchwabDataConsistency:
    """Cross-check consistency between accounts, holdings, and activities."""

    def test_holdings_reference_valid_accounts(self, schwab_client):
        """All holdings from sync_all reference accounts in the result."""
        result = schwab_client.sync_all()
        account_ids = {a.id for a in result.accounts}

        for holding in result.holdings:
            assert holding.account_id in account_ids, (
                f"Holding references unknown account: {holding.account_id}"
            )

    def test_balance_dates_reference_valid_accounts(self, schwab_client):
        """All balance_dates keys from sync_all reference accounts in the result."""
        result = schwab_client.sync_all()
        account_ids = {a.id for a in result.accounts}

        for acct_id in result.balance_dates:
            assert acct_id in account_ids, (
                f"Balance date references unknown account: {acct_id}"
            )
