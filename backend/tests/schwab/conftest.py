"""Pytest fixtures for Schwab integration tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from integrations.schwab_client import SchwabClient


@pytest.fixture(scope="session", autouse=True)
def load_test_env():
    """Load test environment variables from .env.test."""
    env_test_path = Path(__file__).parent.parent.parent / ".env.test"
    if not env_test_path.exists():
        pytest.skip(
            "Schwab test credentials not found. "
            "Copy .env.test.example to .env.test and fill in credentials."
        )
    load_dotenv(env_test_path, override=True)


@pytest.fixture(scope="session")
def schwab_client(load_test_env) -> SchwabClient:
    """Create a real SchwabClient using test credentials.

    Requires SCHWAB_APP_KEY, SCHWAB_APP_SECRET, and SCHWAB_TOKEN_PATH
    to be set in .env.test.  The token file must exist on disk.
    """
    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH")

    if not app_key or not app_secret:
        pytest.skip(
            "Missing Schwab test credentials: "
            "set SCHWAB_APP_KEY and SCHWAB_APP_SECRET in .env.test"
        )

    if not token_path or not Path(token_path).exists():
        pytest.skip(
            "Schwab token file not found: "
            "set SCHWAB_TOKEN_PATH in .env.test and ensure the file exists"
        )

    return SchwabClient(
        app_key=app_key,
        app_secret=app_secret,
        token_path=token_path,
    )
