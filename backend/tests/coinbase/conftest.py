"""Pytest fixtures for Coinbase integration tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from integrations.coinbase_client import CoinbaseClient


@pytest.fixture(scope="session", autouse=True)
def load_test_env():
    """Load test environment variables from .env.test."""
    env_test_path = Path(__file__).parent.parent.parent / ".env.test"
    if not env_test_path.exists():
        pytest.skip(
            "Coinbase test credentials not found. "
            "Copy .env.test.example to .env.test and fill in credentials."
        )
    load_dotenv(env_test_path, override=True)


@pytest.fixture(scope="session")
def coinbase_client(load_test_env) -> CoinbaseClient:
    """Create a real CoinbaseClient using test credentials.

    Supports both key-file and inline key/secret authentication.
    """
    key_file = os.getenv("COINBASE_KEY_FILE")
    api_key = os.getenv("COINBASE_API_KEY")
    api_secret = os.getenv("COINBASE_API_SECRET")

    if key_file:
        return CoinbaseClient(key_file=key_file)

    if not api_key or not api_secret:
        pytest.skip(
            "Missing Coinbase test credentials: "
            "set COINBASE_KEY_FILE or COINBASE_API_KEY + COINBASE_API_SECRET"
        )

    return CoinbaseClient(api_key=api_key, api_secret=api_secret)
