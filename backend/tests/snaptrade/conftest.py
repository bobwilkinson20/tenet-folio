"""Pytest fixtures for SnapTrade integration tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from integrations.snaptrade_client import SnapTradeClient


@pytest.fixture(scope="session", autouse=True)
def load_test_env():
    """Load test environment variables from .env.test."""
    env_test_path = Path(__file__).parent.parent.parent / ".env.test"
    if not env_test_path.exists():
        pytest.skip(
            "SnapTrade test credentials not found. "
            "Copy .env.test.example to .env.test and fill in credentials."
        )
    load_dotenv(env_test_path, override=True)


@pytest.fixture(scope="session")
def snaptrade_client(load_test_env) -> SnapTradeClient:
    """Create a real SnapTrade client using test credentials."""
    # Verify credentials are set
    required_vars = [
        "SNAPTRADE_CLIENT_ID",
        "SNAPTRADE_CONSUMER_KEY",
        "SNAPTRADE_USER_ID",
        "SNAPTRADE_USER_SECRET",
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        pytest.skip(f"Missing SnapTrade test credentials: {missing}")

    # Explicitly pass credentials from env to avoid caching issues with settings
    return SnapTradeClient(
        client_id=os.getenv("SNAPTRADE_CLIENT_ID"),
        consumer_key=os.getenv("SNAPTRADE_CONSUMER_KEY"),
        user_id=os.getenv("SNAPTRADE_USER_ID"),
        user_secret=os.getenv("SNAPTRADE_USER_SECRET"),
    )


@pytest.fixture(name="test_db")
def test_db_fixture():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
