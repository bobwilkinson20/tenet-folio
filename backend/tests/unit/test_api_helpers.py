"""Tests for shared API helpers."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api.helpers import (
    get_latest_account_snapshot,
    get_or_404,
    holding_response_dict,
    security_response_dict,
)
from models import Account, AccountSnapshot, Holding, Security, SyncSession


class TestGetOr404:
    """Tests for get_or_404."""

    def test_returns_entity(self, db):
        """Returns the entity when it exists."""
        account = Account(
            provider_name="Manual",
            external_id="test-ext",
            name="Test Account",
        )
        db.add(account)
        db.commit()

        result = get_or_404(db, Account, account.id, "Account not found")
        assert result.id == account.id
        assert result.name == "Test Account"

    def test_raises_404_when_missing(self, db):
        """Raises HTTPException 404 when the entity doesn't exist."""
        with pytest.raises(HTTPException) as exc_info:
            get_or_404(db, Account, "nonexistent-id", "Account not found")
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Account not found"

    def test_custom_detail_message(self, db):
        """Uses the custom detail message."""
        with pytest.raises(HTTPException) as exc_info:
            get_or_404(db, Security, "missing", "Security not found")
        assert exc_info.value.detail == "Security not found"

    def test_works_with_different_models(self, db):
        """Works with Security model."""
        security = Security(ticker="AAPL", name="Apple Inc.")
        db.add(security)
        db.commit()

        result = get_or_404(db, Security, security.id, "Not found")
        assert result.ticker == "AAPL"


class TestGetLatestAccountSnapshot:
    """Tests for get_latest_account_snapshot."""

    def test_returns_latest_by_timestamp(self, db):
        """Returns the snapshot from the most recent sync session."""
        account = Account(
            provider_name="Manual",
            external_id="test-ext",
            name="Test Account",
        )
        db.add(account)
        db.commit()

        # Create two sync sessions with different timestamps
        old_session = SyncSession(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        new_session = SyncSession(
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        db.add_all([old_session, new_session])
        db.commit()

        old_snap = AccountSnapshot(
            sync_session_id=old_session.id,
            account_id=account.id,
            status="success",
            total_value=Decimal("1000"),
        )
        new_snap = AccountSnapshot(
            sync_session_id=new_session.id,
            account_id=account.id,
            status="success",
            total_value=Decimal("2000"),
        )
        db.add_all([old_snap, new_snap])
        db.commit()

        result = get_latest_account_snapshot(db, account.id)
        assert result is not None
        assert result.id == new_snap.id
        assert result.total_value == Decimal("2000")

    def test_returns_none_when_empty(self, db):
        """Returns None when no snapshots exist for the account."""
        account = Account(
            provider_name="Manual",
            external_id="test-ext",
            name="Test Account",
        )
        db.add(account)
        db.commit()

        result = get_latest_account_snapshot(db, account.id)
        assert result is None

    def test_filters_by_account_id(self, db):
        """Only returns snapshots for the specified account."""
        account1 = Account(
            provider_name="Manual",
            external_id="ext-1",
            name="Account 1",
        )
        account2 = Account(
            provider_name="Manual",
            external_id="ext-2",
            name="Account 2",
        )
        db.add_all([account1, account2])
        db.commit()

        session = SyncSession(
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        db.add(session)
        db.commit()

        snap1 = AccountSnapshot(
            sync_session_id=session.id,
            account_id=account1.id,
            status="success",
            total_value=Decimal("1000"),
        )
        snap2 = AccountSnapshot(
            sync_session_id=session.id,
            account_id=account2.id,
            status="success",
            total_value=Decimal("2000"),
        )
        db.add_all([snap1, snap2])
        db.commit()

        result = get_latest_account_snapshot(db, account1.id)
        assert result is not None
        assert result.account_id == account1.id


class TestHoldingResponseDict:
    """Tests for holding_response_dict."""

    def test_correct_dict_with_security(self):
        """Builds correct dict when security is present."""
        security = MagicMock()
        security.name = "Apple Inc."

        holding = MagicMock(spec=Holding)
        holding.id = "h1"
        holding.account_snapshot_id = "snap1"
        holding.security_id = "sec1"
        holding.ticker = "AAPL"
        holding.quantity = Decimal("10")
        holding.snapshot_price = Decimal("150.00")
        holding.snapshot_value = Decimal("1500.00")
        holding.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        holding.security = security

        result = holding_response_dict(holding)

        assert result["id"] == "h1"
        assert result["ticker"] == "AAPL"
        assert result["security_name"] == "Apple Inc."
        assert result["quantity"] == Decimal("10")

    def test_handles_none_security(self):
        """Builds dict correctly when security is None."""
        holding = MagicMock(spec=Holding)
        holding.id = "h1"
        holding.account_snapshot_id = "snap1"
        holding.security_id = None
        holding.ticker = "UNKNOWN"
        holding.quantity = Decimal("5")
        holding.snapshot_price = Decimal("0")
        holding.snapshot_value = Decimal("0")
        holding.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        holding.security = None

        result = holding_response_dict(holding)

        assert result["security_name"] is None


class TestSecurityResponseDict:
    """Tests for security_response_dict."""

    def test_correct_dict_with_asset_class(self):
        """Builds dict with asset class info when assigned."""
        asset_class = MagicMock()
        asset_class.id = "ac1"
        asset_class.name = "US Equity"
        asset_class.color = "#4CAF50"

        sec = MagicMock(spec=Security)
        sec.id = "s1"
        sec.ticker = "AAPL"
        sec.name = "Apple Inc."
        sec.manual_asset_class_id = "ac1"
        sec.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        sec.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        sec.manual_asset_class = asset_class

        result = security_response_dict(sec)

        assert result["id"] == "s1"
        assert result["ticker"] == "AAPL"
        assert result["asset_type_id"] == "ac1"
        assert result["asset_type_name"] == "US Equity"
        assert result["asset_type_color"] == "#4CAF50"

    def test_handles_none_asset_class(self):
        """Builds dict with null asset type when not assigned."""
        sec = MagicMock(spec=Security)
        sec.id = "s1"
        sec.ticker = "AAPL"
        sec.name = "Apple Inc."
        sec.manual_asset_class_id = None
        sec.created_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        sec.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        sec.manual_asset_class = None

        result = security_response_dict(sec)

        assert result["asset_type_id"] is None
        assert result["asset_type_name"] is None
        assert result["asset_type_color"] is None
