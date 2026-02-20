"""Integration tests for SnapTrade API.

These tests run against the real SnapTrade API using test credentials
connected to a paper trading account.

Run with: pytest -m snaptrade
"""

import pytest

from integrations.snaptrade_client import SnapTradeAccount, SnapTradeHolding


pytestmark = pytest.mark.snaptrade


class TestSnapTradeAccounts:
    """Tests for account fetching from SnapTrade."""

    def test_get_accounts_returns_list(self, snaptrade_client):
        """Fetching accounts returns a list of SnapTradeAccount objects."""
        accounts = snaptrade_client.get_accounts()

        assert isinstance(accounts, list)
        assert len(accounts) > 0, "Expected at least one account in test user"

    def test_account_has_required_fields(self, snaptrade_client):
        """Each account has all required fields populated."""
        accounts = snaptrade_client.get_accounts()
        account = accounts[0]

        assert isinstance(account, SnapTradeAccount)
        assert isinstance(account.id, str)
        assert len(account.id) > 0
        assert isinstance(account.name, str)
        assert isinstance(account.brokerage_name, str)

    def test_account_id_is_string_not_dict(self, snaptrade_client):
        """Account ID is a plain string, not a dict or complex object."""
        accounts = snaptrade_client.get_accounts()

        for account in accounts:
            assert isinstance(account.id, str), f"Account ID should be string, got {type(account.id)}"
            assert not account.id.startswith("{"), "Account ID looks like a dict"


class TestSnapTradeHoldings:
    """Tests for holdings fetching from SnapTrade."""

    def test_get_all_holdings_returns_list(self, snaptrade_client):
        """Fetching holdings returns a list of SnapTradeHolding objects."""
        holdings = snaptrade_client.get_all_holdings()

        assert isinstance(holdings, list)
        # Paper trading account may or may not have holdings

    def test_holding_has_required_fields(self, snaptrade_client):
        """Each holding has all required fields with correct types."""
        holdings = snaptrade_client.get_all_holdings()

        if len(holdings) == 0:
            pytest.skip("No holdings in test account to verify")

        holding = holdings[0]
        assert isinstance(holding, SnapTradeHolding)
        assert isinstance(holding.account_id, str)
        assert isinstance(holding.symbol, str)
        assert isinstance(holding.quantity, float)
        assert isinstance(holding.price, float)
        assert isinstance(holding.market_value, float)
        assert isinstance(holding.currency, str)

    def test_holding_symbol_is_string_not_dict(self, snaptrade_client):
        """Holding symbol is a plain string, not a dict or complex object."""
        holdings = snaptrade_client.get_all_holdings()

        if len(holdings) == 0:
            pytest.skip("No holdings in test account to verify")

        for holding in holdings:
            assert isinstance(holding.symbol, str), f"Symbol should be string, got {type(holding.symbol)}"
            assert not holding.symbol.startswith("{"), f"Symbol looks like a dict: {holding.symbol}"
            assert holding.symbol != "UNKNOWN", "Symbol was not parsed correctly"

    def test_holding_values_are_reasonable(self, snaptrade_client):
        """Holding numeric values are non-negative and sensible."""
        holdings = snaptrade_client.get_all_holdings()

        if len(holdings) == 0:
            pytest.skip("No holdings in test account to verify")

        for holding in holdings:
            assert holding.quantity >= 0, f"Quantity should be non-negative: {holding.quantity}"
            assert holding.price >= 0, f"Price should be non-negative: {holding.price}"
            assert holding.market_value >= 0, f"Market value should be non-negative: {holding.market_value}"

    def test_holding_currency_is_valid(self, snaptrade_client):
        """Holding currency is a valid currency code."""
        holdings = snaptrade_client.get_all_holdings()

        if len(holdings) == 0:
            pytest.skip("No holdings in test account to verify")

        valid_currencies = {"USD", "CAD", "EUR", "GBP", "JPY", "AUD", "CHF"}
        for holding in holdings:
            assert len(holding.currency) == 3, f"Currency should be 3-letter code: {holding.currency}"
            # Allow any 3-letter code, but warn if not common
            if holding.currency not in valid_currencies:
                print(f"Note: Unusual currency code: {holding.currency}")


class TestSnapTradeDataConsistency:
    """Tests for data consistency between accounts and holdings."""

    def test_holdings_reference_valid_accounts(self, snaptrade_client):
        """All holdings reference an account that exists."""
        accounts = snaptrade_client.get_accounts()
        account_ids = {account.id for account in accounts}

        holdings = snaptrade_client.get_all_holdings()

        for holding in holdings:
            assert holding.account_id in account_ids, (
                f"Holding references unknown account: {holding.account_id}"
            )

    def test_market_value_calculation(self, snaptrade_client):
        """Market value equals quantity times price (within rounding)."""
        holdings = snaptrade_client.get_all_holdings()

        if len(holdings) == 0:
            pytest.skip("No holdings in test account to verify")

        for holding in holdings:
            expected = holding.quantity * holding.price
            # Allow small rounding differences
            assert abs(holding.market_value - expected) < 0.01, (
                f"Market value mismatch for {holding.symbol}: "
                f"{holding.market_value} != {holding.quantity} * {holding.price}"
            )
