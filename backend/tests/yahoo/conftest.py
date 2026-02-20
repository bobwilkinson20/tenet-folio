"""Yahoo Finance integration test fixtures."""

import pytest

from integrations.yahoo_finance_client import YahooFinanceClient


@pytest.fixture
def yahoo_client():
    """Create a real YahooFinanceClient for integration tests."""
    return YahooFinanceClient()
