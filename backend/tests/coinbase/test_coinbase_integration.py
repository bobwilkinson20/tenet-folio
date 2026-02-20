"""Integration tests for Coinbase Advanced Trade API.

These tests run against the real Coinbase API using test credentials.
The client is created once per session to minimize API calls.

Run with: pytest -m coinbase
"""

from decimal import Decimal

import pytest

from integrations.provider_protocol import (
    ProviderAccount,
    ProviderActivity,
    ProviderHolding,
    ProviderSyncResult,
)


pytestmark = pytest.mark.coinbase


class TestCoinbaseAccounts:
    """Tests for account (portfolio) fetching."""

    def test_get_accounts_returns_list(self, coinbase_client):
        """Fetching accounts returns a non-empty list."""
        accounts = coinbase_client.get_accounts()

        assert isinstance(accounts, list)
        assert len(accounts) > 0, "Expected at least one portfolio"

    def test_account_has_required_fields(self, coinbase_client):
        """Each account has all required fields populated."""
        accounts = coinbase_client.get_accounts()
        account = accounts[0]

        assert isinstance(account, ProviderAccount)
        assert isinstance(account.id, str)
        assert len(account.id) > 0
        assert isinstance(account.name, str)
        assert len(account.name) > 0
        assert account.institution == "Coinbase"


class TestCoinbaseHoldings:
    """Tests for holdings fetching."""

    def test_get_holdings_returns_list(self, coinbase_client):
        """Fetching holdings returns a list."""
        holdings = coinbase_client.get_holdings()

        assert isinstance(holdings, list)

    def test_holding_has_required_fields(self, coinbase_client):
        """Each holding has required fields with correct types."""
        holdings = coinbase_client.get_holdings()

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

    def test_holdings_reference_valid_accounts(self, coinbase_client):
        """All holdings reference an account that exists."""
        accounts = coinbase_client.get_accounts()
        account_ids = {a.id for a in accounts}

        holdings = coinbase_client.get_holdings()

        for holding in holdings:
            assert holding.account_id in account_ids, (
                f"Holding references unknown account: {holding.account_id}"
            )


class TestCoinbaseActivities:
    """Tests for activity (fills + v2 transactions) fetching."""

    def test_get_activities_returns_list(self, coinbase_client):
        """Fetching activities returns a list."""
        accounts = coinbase_client.get_accounts()
        assert len(accounts) > 0

        activities = coinbase_client.get_activities(account_id=accounts[0].id)
        assert isinstance(activities, list)

    def test_activity_has_required_fields(self, coinbase_client):
        """Each activity has required fields populated."""
        accounts = coinbase_client.get_accounts()
        activities = coinbase_client.get_activities(account_id=accounts[0].id)

        if len(activities) == 0:
            pytest.skip("No activities in test account to verify")

        activity = activities[0]
        assert isinstance(activity, ProviderActivity)
        assert isinstance(activity.external_id, str)
        assert len(activity.external_id) > 0
        assert isinstance(activity.type, str)
        assert activity.activity_date is not None

    def test_v2_prefixed_ids_present(self, coinbase_client):
        """V2 transactions have 'v2:' prefixed external IDs."""
        accounts = coinbase_client.get_accounts()
        activities = coinbase_client.get_activities(account_id=accounts[0].id)

        v2_activities = [a for a in activities if a.external_id.startswith("v2:")]
        # It's possible a test account has no v2 transactions
        if len(v2_activities) == 0:
            pytest.skip("No v2 transactions found in test account")

        for a in v2_activities:
            assert a.external_id.startswith("v2:")
            assert len(a.external_id) > 3  # more than just "v2:"


class TestCoinbaseSyncAll:
    """Tests for sync_all() orchestration."""

    def test_sync_all_returns_complete_result(self, coinbase_client):
        """sync_all returns accounts, holdings, and no errors."""
        result = coinbase_client.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.accounts) > 0
        assert len(result.holdings) >= 0
        assert len(result.balance_dates) > 0
        assert result.errors == []

    def test_sync_all_activities_populated(self, coinbase_client):
        """sync_all includes activities in the result."""
        result = coinbase_client.sync_all()

        assert isinstance(result.activities, list)
        # Activities may be empty if the account has no trades


class TestCoinbaseDataConsistency:
    """Cross-check consistency between accounts, holdings, and activities."""

    def test_holdings_reference_valid_accounts(self, coinbase_client):
        """All holdings from sync_all reference accounts in the result."""
        result = coinbase_client.sync_all()
        account_ids = {a.id for a in result.accounts}

        for holding in result.holdings:
            assert holding.account_id in account_ids, (
                f"Holding references unknown account: {holding.account_id}"
            )

    def test_activity_account_ids_match_portfolios(self, coinbase_client):
        """All activity account_ids from sync_all reference accounts in the result."""
        result = coinbase_client.sync_all()
        account_ids = {a.id for a in result.accounts}

        for activity in result.activities:
            assert activity.account_id in account_ids, (
                f"Activity references unknown account: {activity.account_id}"
            )
