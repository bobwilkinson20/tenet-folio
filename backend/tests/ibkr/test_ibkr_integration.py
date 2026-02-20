"""Integration tests for IBKR Flex Web Service.

These tests run against the real IBKR Flex API using test credentials.
The Flex report is downloaded exactly ONCE per session (via the
flex_response and ibkr_client fixtures) to respect IBKR rate limits.

Run with: pytest -m ibkr
"""

from decimal import Decimal

import pytest

from integrations.provider_protocol import (
    ProviderAccount,
    ProviderHolding,
    ProviderSyncResult,
)


pytestmark = pytest.mark.ibkr


class TestIBKRQueryValidation:
    """Validate that the Flex Query has required sections."""

    def test_flex_report_has_open_positions(self, flex_response):
        """Flex report includes the Open Positions section."""
        for stmt in flex_response.FlexStatements:
            assert isinstance(stmt.OpenPositions, tuple)

    def test_flex_report_has_cash_report(self, flex_response):
        """Flex report includes the Cash Report section."""
        for stmt in flex_response.FlexStatements:
            assert isinstance(stmt.CashReport, tuple)

    def test_flex_report_has_trades(self, flex_response):
        """Flex report includes the Trades section."""
        for stmt in flex_response.FlexStatements:
            assert isinstance(stmt.Trades, tuple)


class TestIBKRAccounts:
    """Tests for account extraction from the Flex report."""

    def test_get_accounts_returns_list(self, ibkr_client):
        """Fetching accounts returns a non-empty list."""
        accounts = ibkr_client.get_accounts()

        assert isinstance(accounts, list)
        assert len(accounts) > 0, "Expected at least one account"

    def test_account_has_required_fields(self, ibkr_client):
        """Each account has all required fields populated."""
        accounts = ibkr_client.get_accounts()
        account = accounts[0]

        assert isinstance(account, ProviderAccount)
        assert isinstance(account.id, str)
        assert len(account.id) > 0
        assert isinstance(account.name, str)
        assert len(account.name) > 0
        assert account.institution == "Interactive Brokers"


class TestIBKRHoldings:
    """Tests for holdings extraction from the Flex report."""

    def test_get_holdings_returns_list(self, ibkr_client):
        """Fetching holdings returns a list."""
        holdings = ibkr_client.get_holdings()

        assert isinstance(holdings, list)

    def test_holding_has_required_fields(self, ibkr_client):
        """Each holding has required fields with correct types."""
        holdings = ibkr_client.get_holdings()

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

    def test_holdings_reference_valid_accounts(self, ibkr_client):
        """All holdings reference an account that exists."""
        accounts = ibkr_client.get_accounts()
        account_ids = {a.id for a in accounts}

        holdings = ibkr_client.get_holdings()

        for holding in holdings:
            assert holding.account_id in account_ids, (
                f"Holding references unknown account: {holding.account_id}"
            )


class TestIBKRSyncAll:
    """Tests for sync_all() orchestration."""

    def test_sync_all_returns_complete_result(self, ibkr_client):
        """sync_all returns accounts, holdings, balance_dates, and no errors."""
        result = ibkr_client.sync_all()

        assert isinstance(result, ProviderSyncResult)
        assert len(result.accounts) > 0
        assert len(result.holdings) >= 0
        assert len(result.balance_dates) > 0
        assert result.errors == []
