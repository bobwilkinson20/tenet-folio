"""Service for asset type management."""

import logging
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Account, AssetClass, Security

logger = logging.getLogger(__name__)

# Default color palette for new asset types
DEFAULT_COLORS = [
    "#3B82F6",  # Blue
    "#10B981",  # Green
    "#F59E0B",  # Amber
    "#EF4444",  # Red
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#F97316",  # Orange
]


class AssetTypeService:
    """Service for managing asset types (asset classes)."""

    def list_all(self, db: Session) -> List[AssetClass]:
        """Get all asset types ordered by name."""
        return db.query(AssetClass).order_by(AssetClass.name).all()

    def get_by_id(self, db: Session, id: str) -> Optional[AssetClass]:
        """Get single asset type by ID."""
        return db.query(AssetClass).filter_by(id=id).first()

    def get_next_color(self, db: Session) -> str:
        """Get next color from palette based on existing types."""
        existing_count = db.query(AssetClass).count()
        return DEFAULT_COLORS[existing_count % len(DEFAULT_COLORS)]

    def get_total_target_percent(
        self, db: Session, exclude_id: Optional[str] = None
    ) -> Decimal:
        """Sum of all target percentages, optionally excluding one type."""
        query = db.query(func.sum(AssetClass.target_percent))
        if exclude_id:
            query = query.filter(AssetClass.id != exclude_id)
        result = query.scalar()
        return result or Decimal("0.00")

    def create(self, db: Session, name: str, color: str) -> AssetClass:
        """
        Create new asset type.

        Args:
            db: Database session
            name: Asset type name (must be unique)
            color: Hex color code

        Returns:
            Created AssetClass

        Raises:
            HTTPException: If name already exists
        """
        # Check unique name (case-insensitive)
        existing = (
            db.query(AssetClass)
            .filter(func.lower(AssetClass.name) == name.lower())
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400, detail=f"Asset type '{name}' already exists"
            )

        asset_type = AssetClass(name=name, color=color, target_percent=Decimal("0.00"))
        db.add(asset_type)
        db.commit()
        db.refresh(asset_type)
        logger.info("Asset type created: %s (id=%s)", name, asset_type.id)
        return asset_type

    def update(
        self,
        db: Session,
        id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        target_percent: Optional[Decimal] = None,
    ) -> AssetClass:
        """
        Update an asset type.

        Args:
            db: Database session
            id: Asset type ID
            name: New name (optional)
            color: New color (optional)
            target_percent: New target percentage (optional)

        Returns:
            Updated AssetClass

        Raises:
            HTTPException: If asset type not found or name conflict
        """
        asset_type = self.get_by_id(db, id)
        if not asset_type:
            raise HTTPException(status_code=404, detail="Asset type not found")

        # Check unique name if changing (case-insensitive)
        if name is not None and name != asset_type.name:
            existing = (
                db.query(AssetClass)
                .filter(func.lower(AssetClass.name) == name.lower(), AssetClass.id != id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=400, detail=f"Asset type '{name}' already exists"
                )
            asset_type.name = name

        if color is not None:
            asset_type.color = color

        if target_percent is not None:
            asset_type.target_percent = target_percent

        db.commit()
        db.refresh(asset_type)
        logger.info("Asset type updated: %s (id=%s)", asset_type.name, id)
        return asset_type

    def delete(self, db: Session, id: str) -> None:
        """
        Delete an asset type if no assignments exist.

        Args:
            db: Database session
            id: Asset type ID

        Raises:
            HTTPException: If not found or has assignments
        """
        asset_type = self.get_by_id(db, id)
        if not asset_type:
            raise HTTPException(status_code=404, detail="Asset type not found")

        # Check for security assignments
        security_count = (
            db.query(Security).filter_by(manual_asset_class_id=id).count()
        )

        # Check for account assignments
        account_count = db.query(Account).filter_by(assigned_asset_class_id=id).count()

        if security_count > 0 or account_count > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot delete: {security_count} securities and "
                    f"{account_count} accounts assigned to this type"
                ),
            )

        db.delete(asset_type)
        db.commit()
        logger.info("Asset type deleted: %s (id=%s)", asset_type.name, id)

    def get_assignment_counts(self, db: Session, id: str) -> dict:
        """
        Get count of securities and accounts assigned to this type.

        Args:
            db: Database session
            id: Asset type ID

        Returns:
            Dict with security_count and account_count
        """
        security_count = (
            db.query(Security).filter_by(manual_asset_class_id=id).count()
        )
        account_count = db.query(Account).filter_by(assigned_asset_class_id=id).count()

        return {
            "security_count": security_count,
            "account_count": account_count,
        }

    def seed_default_asset_classes(self, db: Session) -> None:
        """Seed default asset classes on a fresh database.

        If any asset classes already exist, this is a no-op.
        """
        existing_count = db.query(AssetClass).count()
        if existing_count > 0:
            logger.info("Asset classes already exist, skipping seed")
            return

        default_names = [
            "Bonds",
            "Cash",
            "Crypto",
            "Intl Equity",
            "Momentum",
            "Other",
            "Spec Stocks",
            "US Equity",
        ]

        for i, name in enumerate(default_names):
            asset_class = AssetClass(
                name=name,
                color=DEFAULT_COLORS[i],
                target_percent=Decimal("0.00"),
            )
            db.add(asset_class)

        db.commit()
        logger.info("Seeded %d default asset classes", len(default_names))

    def update_all_targets(
        self, db: Session, allocations: List[dict]
    ) -> List[AssetClass]:
        """
        Update target_percent for multiple asset types.

        Args:
            db: Database session
            allocations: List of {asset_type_id, target_percent} dicts

        Returns:
            List of updated AssetClass objects

        Raises:
            HTTPException: If targets don't sum to 100%
        """
        total = sum(Decimal(str(a["target_percent"])) for a in allocations)
        if total != Decimal("100.00"):
            raise HTTPException(
                status_code=400,
                detail=f"Target allocations must sum to 100%, got {total}%",
            )

        updated = []
        for alloc in allocations:
            asset_type = self.get_by_id(db, alloc["asset_type_id"])
            if asset_type:
                asset_type.target_percent = Decimal(str(alloc["target_percent"]))
                updated.append(asset_type)

        db.commit()
        logger.info(
            "Allocation targets updated for %d asset types", len(updated),
        )
        return updated
