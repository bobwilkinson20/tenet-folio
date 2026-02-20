"""Tests for AssetTypeService."""

import pytest
from decimal import Decimal
from fastapi import HTTPException

from models import AssetClass, Security, Account
from services.asset_type_service import AssetTypeService, DEFAULT_COLORS


class TestAssetTypeService:
    """Tests for AssetTypeService."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return AssetTypeService()

    def test_list_all_empty(self, service, db):
        """Test listing asset types when none exist."""
        types = service.list_all(db)
        assert len(types) == 0

    def test_list_all_with_data(self, service, db):
        """Test listing asset types with data."""
        # Create some asset types
        type1 = AssetClass(name="US Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        type2 = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([type1, type2])
        db.commit()

        types = service.list_all(db)
        assert len(types) == 2
        # Results are ordered by name
        names = [t.name for t in types]
        assert "US Stocks" in names
        assert "Bonds" in names

    def test_get_by_id_exists(self, service, db):
        """Test getting asset type by ID."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        result = service.get_by_id(db, asset_type.id)
        assert result is not None
        assert result.name == "US Stocks"
        assert result.color == "#3B82F6"

    def test_get_by_id_not_found(self, service, db):
        """Test getting non-existent asset type."""
        result = service.get_by_id(db, "nonexistent-id")
        assert result is None

    def test_create_asset_type(self, service, db):
        """Test creating a new asset type."""
        asset_type = service.create(db, name="US Stocks", color="#3B82F6")

        assert asset_type.name == "US Stocks"
        assert asset_type.color == "#3B82F6"
        assert asset_type.target_percent == Decimal("0.00")

        # Verify in database
        db_type = db.query(AssetClass).filter_by(id=asset_type.id).first()
        assert db_type is not None
        assert db_type.name == "US Stocks"

    def test_create_duplicate_name(self, service, db):
        """Test creating asset type with duplicate name fails."""
        service.create(db, name="US Stocks", color="#3B82F6")

        with pytest.raises(HTTPException) as exc_info:
            service.create(db, name="US Stocks", color="#10B981")
        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)

    def test_update_asset_type(self, service, db):
        """Test updating asset type."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        updated = service.update(
            db, asset_type.id, name="US Equities", color="#F59E0B"
        )

        assert updated.name == "US Equities"
        assert updated.color == "#F59E0B"

    def test_update_to_duplicate_name(self, service, db):
        """Test updating to duplicate name fails."""
        type1 = AssetClass(name="US Stocks", color="#3B82F6")
        type2 = AssetClass(name="Bonds", color="#10B981")
        db.add_all([type1, type2])
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            service.update(db, type2.id, name="US Stocks")
        assert exc_info.value.status_code == 400

    def test_delete_asset_type(self, service, db):
        """Test deleting asset type."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()
        type_id = asset_type.id

        service.delete(db, type_id)

        # Verify deleted
        result = db.query(AssetClass).filter_by(id=type_id).first()
        assert result is None

    def test_delete_with_assignments_fails(self, service, db):
        """Test deleting asset type with assignments fails."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        security = Security(ticker="AAPL", manual_asset_class=asset_type)
        db.add_all([asset_type, security])
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            service.delete(db, asset_type.id)
        assert exc_info.value.status_code == 400
        assert "assigned" in str(exc_info.value.detail).lower()

    def test_get_assignment_counts(self, service, db):
        """Test getting asset type assignment counts."""
        asset_type = AssetClass(name="US Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        # Add assignments
        security = Security(ticker="AAPL", manual_asset_class=asset_type)
        account = Account(
            provider_name="Test",
            external_id="test-123",
            name="Test Account",
            assigned_asset_class=asset_type,
        )
        db.add_all([security, account])
        db.commit()

        result = service.get_assignment_counts(db, asset_type.id)
        assert result["security_count"] == 1
        assert result["account_count"] == 1

    def test_get_total_target_percent(self, service, db):
        """Test getting total target percentage."""
        type1 = AssetClass(name="US Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        type2 = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([type1, type2])
        db.commit()

        total = service.get_total_target_percent(db)
        assert total == Decimal("100.00")

    def test_update_all_targets_valid(self, service, db):
        """Test updating all targets with valid 100% total."""
        type1 = AssetClass(name="US Stocks", color="#3B82F6")
        type2 = AssetClass(name="Bonds", color="#10B981")
        db.add_all([type1, type2])
        db.commit()

        allocations = [
            {"asset_type_id": type1.id, "target_percent": "70.00"},
            {"asset_type_id": type2.id, "target_percent": "30.00"},
        ]

        result = service.update_all_targets(db, allocations)
        assert len(result) == 2
        assert result[0].target_percent == Decimal("70.00")
        assert result[1].target_percent == Decimal("30.00")

    def test_update_all_targets_invalid_total(self, service, db):
        """Test updating targets with invalid total fails."""
        type1 = AssetClass(name="US Stocks", color="#3B82F6")
        type2 = AssetClass(name="Bonds", color="#10B981")
        db.add_all([type1, type2])
        db.commit()

        allocations = [
            {"asset_type_id": type1.id, "target_percent": "60.00"},
            {"asset_type_id": type2.id, "target_percent": "30.00"},  # Total = 90%
        ]

        with pytest.raises(HTTPException) as exc_info:
            service.update_all_targets(db, allocations)
        assert exc_info.value.status_code == 400
        assert "100%" in str(exc_info.value.detail)

    def test_update_all_targets_missing_type(self, service, db):
        """Test updating targets with non-existent type is skipped."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        allocations = [
            {"asset_type_id": "nonexistent", "target_percent": "50.00"},
            {"asset_type_id": asset_type.id, "target_percent": "50.00"},
        ]

        # Should not raise - non-existent IDs are skipped
        result = service.update_all_targets(db, allocations)
        # Only the valid one is returned
        assert len(result) == 1
        assert result[0].id == asset_type.id

    def test_get_next_color_cycles(self, service, db):
        """Test color selection cycles through palette."""
        # Create 8 types (full palette)
        colors = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4", "#F97316"]
        for i, color in enumerate(colors):
            asset_type = AssetClass(name=f"Type {i}", color=color)
            db.add(asset_type)
        db.commit()

        # Next color should cycle back to first
        next_color = service.get_next_color(db)
        assert next_color == "#3B82F6"

    def test_seed_default_asset_classes_fresh_db(self, service, db):
        """Test seeding default asset classes on empty database."""
        service.seed_default_asset_classes(db)

        classes = db.query(AssetClass).order_by(AssetClass.name).all()
        assert len(classes) == 8

        expected_names = [
            "Bonds", "Cash", "Crypto", "Intl Equity",
            "Momentum", "Other", "Spec Stocks", "US Equity",
        ]
        assert [c.name for c in classes] == expected_names

        # All targets should be 0%
        for c in classes:
            assert c.target_percent == Decimal("0.00")

        # Colors should be assigned from DEFAULT_COLORS in order
        for i, c in enumerate(sorted(classes, key=lambda x: expected_names.index(x.name))):
            assert c.color == DEFAULT_COLORS[i]

    def test_seed_default_asset_classes_skips_when_exists(self, service, db):
        """Test seeding is skipped when asset classes already exist."""
        existing = AssetClass(name="Custom", color="#123456", target_percent=Decimal("50.00"))
        db.add(existing)
        db.commit()

        service.seed_default_asset_classes(db)

        classes = db.query(AssetClass).all()
        assert len(classes) == 1
        assert classes[0].name == "Custom"
        assert classes[0].target_percent == Decimal("50.00")
