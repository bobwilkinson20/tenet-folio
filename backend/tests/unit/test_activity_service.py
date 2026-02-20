"""Tests for ActivityService."""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from integrations.provider_protocol import ProviderActivity
from models import Account
from models.activity import Activity
from services.activity_service import ActivityService


@pytest.fixture
def test_account(db: Session) -> Account:
    """Create a test account for activity tests."""
    acc = Account(
        provider_name="SnapTrade",
        external_id="ext_act_test",
        name="Activity Test Account",
        institution_name="Test Brokerage",
        is_active=True,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def _make_activity(
    account_id: str = "ext_act_test",
    external_id: str = "act_001",
    **kwargs,
) -> ProviderActivity:
    """Helper to create a ProviderActivity."""
    defaults = {
        "account_id": account_id,
        "external_id": external_id,
        "activity_date": datetime(2025, 1, 15, tzinfo=timezone.utc),
        "type": "buy",
        "description": "Bought AAPL",
        "ticker": "AAPL",
        "units": Decimal("10"),
        "price": Decimal("150.50"),
        "amount": Decimal("1505.00"),
        "currency": "USD",
    }
    defaults.update(kwargs)
    return ProviderActivity(**defaults)


class TestActivityServiceSync:
    """Tests for ActivityService.sync_activities."""

    def test_inserts_new_activities(self, db: Session, test_account: Account):
        activities = [
            _make_activity(external_id="act_001"),
            _make_activity(external_id="act_002", ticker="GOOGL"),
        ]

        count = ActivityService.sync_activities(
            db, "SnapTrade", test_account, activities
        )
        db.commit()

        assert count == 2
        stored = db.query(Activity).filter(Activity.account_id == test_account.id).all()
        assert len(stored) == 2

    def test_deduplicates_existing_activities(self, db: Session, test_account: Account):
        # Insert first
        activities = [_make_activity(external_id="act_001")]
        ActivityService.sync_activities(db, "SnapTrade", test_account, activities)
        db.commit()

        # Insert again with same external_id + a new one
        activities = [
            _make_activity(external_id="act_001"),
            _make_activity(external_id="act_002"),
        ]
        count = ActivityService.sync_activities(
            db, "SnapTrade", test_account, activities
        )
        db.commit()

        assert count == 1  # Only the new one
        stored = db.query(Activity).filter(Activity.account_id == test_account.id).all()
        assert len(stored) == 2

    def test_empty_list_returns_zero(self, db: Session, test_account: Account):
        count = ActivityService.sync_activities(db, "SnapTrade", test_account, [])
        assert count == 0

    def test_raw_data_serialized_as_json(self, db: Session, test_account: Account):
        raw = {"id": "act_001", "type": "BUY", "nested": {"key": "value"}}
        activities = [_make_activity(external_id="act_001", raw_data=raw)]
        ActivityService.sync_activities(db, "SnapTrade", test_account, activities)
        db.commit()

        stored = db.query(Activity).filter(
            Activity.external_id == "act_001"
        ).first()
        assert stored is not None
        parsed = json.loads(stored.raw_data)
        assert parsed["nested"]["key"] == "value"

    def test_nullable_fields_stored_correctly(self, db: Session, test_account: Account):
        activities = [
            _make_activity(
                external_id="act_null",
                ticker=None,
                units=None,
                price=None,
                fee=None,
                settlement_date=None,
                description=None,
                raw_data=None,
            )
        ]
        ActivityService.sync_activities(db, "SnapTrade", test_account, activities)
        db.commit()

        stored = db.query(Activity).filter(
            Activity.external_id == "act_null"
        ).first()
        assert stored is not None
        assert stored.ticker is None
        assert stored.units is None
        assert stored.price is None
        assert stored.fee is None
        assert stored.settlement_date is None
        assert stored.description is None
        assert stored.raw_data is None

    def test_raw_data_with_non_serializable_values(
        self, db: Session, test_account: Account
    ):
        """Test that raw_data with datetime values gets serialized using default=str."""
        raw = {"id": "act_dt", "date": datetime(2025, 1, 15, tzinfo=timezone.utc)}
        activities = [_make_activity(external_id="act_dt", raw_data=raw)]
        ActivityService.sync_activities(db, "SnapTrade", test_account, activities)
        db.commit()

        stored = db.query(Activity).filter(
            Activity.external_id == "act_dt"
        ).first()
        assert stored is not None
        parsed = json.loads(stored.raw_data)
        assert "2025" in parsed["date"]

    def test_multiple_accounts_independent_dedup(self, db: Session):
        """Activities with same external_id but different accounts are not deduped."""
        acc1 = Account(
            provider_name="SnapTrade",
            external_id="ext_1",
            name="Account 1",
            is_active=True,
        )
        acc2 = Account(
            provider_name="SnapTrade",
            external_id="ext_2",
            name="Account 2",
            is_active=True,
        )
        db.add_all([acc1, acc2])
        db.commit()
        db.refresh(acc1)
        db.refresh(acc2)

        activities = [_make_activity(external_id="same_id")]

        count1 = ActivityService.sync_activities(db, "SnapTrade", acc1, activities)
        count2 = ActivityService.sync_activities(db, "SnapTrade", acc2, activities)
        db.commit()

        assert count1 == 1
        assert count2 == 1
        total = db.query(Activity).count()
        assert total == 2
