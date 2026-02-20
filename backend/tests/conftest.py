"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from api.providers import get_registry as get_registry_for_providers
from api.sync import get_sync_service as get_sync_service_for_sync
from services.sync_service import SyncService
# Pytest fixtures - imported to make them available to tests
from tests.fixtures import (  # noqa: F401
    activity,
    asset_class,
    account,
    account_without_asset_class,
    holding_lot,
    lot_disposal,
    security,
    sync_session,
    holding,
    sync_log_entry,
    account_snapshot,
)
from tests.fixtures.mocks import (
    MockSnapTradeClient,
    MockProviderRegistry,
    SAMPLE_SNAPTRADE_ACCOUNTS,
    SAMPLE_SNAPTRADE_HOLDINGS,
)

@pytest.fixture(name="db")
def db_fixture():
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


@pytest.fixture(name="client")
def client_fixture(db):
    """Create a test client with the test database."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    # Provide a mock registry with an empty SnapTrade client
    mock_client = MockSnapTradeClient()
    mock_registry = MockProviderRegistry({"SnapTrade": mock_client})

    def override_get_sync_service():
        return SyncService(provider_registry=mock_registry)

    def override_get_registry():
        return mock_registry

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_get_sync_service
    app.dependency_overrides[get_registry_for_providers] = override_get_registry
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="mock_snaptrade_client")
def mock_snaptrade_client_fixture():
    """Create a mock SnapTrade client with sample data."""
    return MockSnapTradeClient(
        accounts=SAMPLE_SNAPTRADE_ACCOUNTS,
        holdings=SAMPLE_SNAPTRADE_HOLDINGS,
    )


@pytest.fixture(name="mock_provider_registry")
def mock_provider_registry_fixture(mock_snaptrade_client):
    """Create a mock provider registry with sample data."""
    return MockProviderRegistry({"SnapTrade": mock_snaptrade_client})


@pytest.fixture(name="client_with_mock_sync")
def client_with_mock_sync_fixture(db, mock_provider_registry):
    """Create a test client with mocked SyncService."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_get_sync_service():
        return SyncService(provider_registry=mock_provider_registry)

    def override_get_registry():
        return mock_provider_registry

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_get_sync_service
    app.dependency_overrides[get_registry_for_providers] = override_get_registry
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="client_with_failing_sync")
def client_with_failing_sync_fixture(db):
    """Create a test client with a SyncService that always fails."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    failing_client = MockSnapTradeClient(
        should_fail=True, failure_message="SnapTrade API unavailable"
    )
    failing_registry = MockProviderRegistry({"SnapTrade": failing_client})

    def override_get_sync_service():
        return SyncService(provider_registry=failing_registry)

    def override_get_registry():
        return failing_registry

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_sync_service_for_sync] = override_get_sync_service
    app.dependency_overrides[get_registry_for_providers] = override_get_registry
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
