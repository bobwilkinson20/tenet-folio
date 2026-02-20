"""Pytest fixtures for IBKR Flex integration tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from integrations.ibkr_flex_client import IBKRFlexClient


@pytest.fixture(scope="session", autouse=True)
def load_test_env():
    """Load test environment variables from .env.test."""
    env_test_path = Path(__file__).parent.parent.parent / ".env.test"
    if not env_test_path.exists():
        pytest.skip(
            "IBKR test credentials not found. "
            "Copy .env.test.example to .env.test and fill in credentials."
        )
    load_dotenv(env_test_path, override=True)


@pytest.fixture(scope="session")
def ibkr_client(load_test_env) -> IBKRFlexClient:
    """Create a real IBKRFlexClient using test credentials.

    The client caches the Flex report after the first download,
    so all tests in the session share a single API call.
    """
    token = os.getenv("IBKR_FLEX_TOKEN")
    query_id = os.getenv("IBKR_FLEX_QUERY_ID")

    if not token or not query_id:
        pytest.skip("Missing IBKR test credentials: IBKR_FLEX_TOKEN and/or IBKR_FLEX_QUERY_ID")

    return IBKRFlexClient(token=token, query_id=query_id)


@pytest.fixture(scope="session")
def flex_response(ibkr_client):
    """Download the Flex report once for the entire test session.

    All integration tests should use this fixture (or ibkr_client,
    which caches internally) to avoid hitting IBKR rate limits.
    """
    return ibkr_client._fetch_statement()
