"""Service for lot-based cost basis tracking.

Pure data layer for CRUD, queries, aggregation, and disposal management
of HoldingLot and LotDisposal records. Has no knowledge of Holdings —
the lots-match-holdings invariant is enforced by the reconciliation engine.
"""

import logging
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from models import HoldingLot, LotDisposal, Security, generate_uuid
from schemas.lot import (
    DisposalReassignRequest,
    HoldingLotCreate,
    HoldingLotUpdate,
    LotBatchCreate,
    LotBatchUpdate,
)

logger = logging.getLogger(__name__)


class LotLedgerService:
    """Manages lot CRUD, queries, aggregation, and disposal reassignment."""

    # --- CRUD ---

    @staticmethod
    def create_lot(
        db: Session, account_id: str, lot_data: HoldingLotCreate
    ) -> HoldingLot:
        """Create a manual holding lot.

        Resolves ticker to a Security record. Raises ValueError if the
        security doesn't exist (lots should only reference known securities).
        """
        security = db.query(Security).filter_by(ticker=lot_data.ticker).first()
        if not security:
            raise ValueError(f"Unknown security ticker: {lot_data.ticker}")

        lot = HoldingLot(
            account_id=account_id,
            security_id=security.id,
            ticker=lot_data.ticker,
            acquisition_date=lot_data.acquisition_date,
            cost_basis_per_unit=lot_data.cost_basis_per_unit,
            original_quantity=lot_data.quantity,
            current_quantity=lot_data.quantity,
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()
        logger.info(
            "Created lot: %s shares of %s in account %s",
            lot_data.quantity,
            lot_data.ticker,
            account_id,
        )
        return lot

    @staticmethod
    def update_lot(
        db: Session, lot_id: str, lot_data: HoldingLotUpdate
    ) -> HoldingLot:
        """Update a holding lot.

        Only manual/inferred/initial lots can be edited. Activity-sourced
        lots are immutable. When quantity is provided, it represents the
        new original_quantity; current_quantity is adjusted to preserve
        the disposed amount.
        """
        lot = db.query(HoldingLot).filter_by(id=lot_id).first()
        if not lot:
            raise ValueError(f"Lot not found: {lot_id}")

        if lot.source == "activity":
            raise ValueError("Cannot edit activity-sourced lots")

        if lot_data.acquisition_date is not None:
            lot.acquisition_date = lot_data.acquisition_date

        if lot_data.cost_basis_per_unit is not None:
            lot.cost_basis_per_unit = lot_data.cost_basis_per_unit

        if lot_data.quantity is not None:
            disposed = lot.original_quantity - lot.current_quantity
            if lot_data.quantity < disposed:
                raise ValueError(
                    f"New quantity ({lot_data.quantity}) cannot be less than "
                    f"already-disposed amount ({disposed})"
                )
            lot.original_quantity = lot_data.quantity
            lot.current_quantity = lot_data.quantity - disposed
            lot.is_closed = lot.current_quantity == 0

        db.flush()
        logger.info("Updated lot: %s", lot_id)
        return lot

    @staticmethod
    def delete_lot(db: Session, lot_id: str) -> None:
        """Delete a holding lot.

        Only manual/inferred/initial lots can be deleted. Activity-sourced
        lots are immutable. Cascade handles associated disposals.
        """
        lot = db.query(HoldingLot).filter_by(id=lot_id).first()
        if not lot:
            raise ValueError(f"Lot not found: {lot_id}")

        if lot.source == "activity":
            raise ValueError("Cannot delete activity-sourced lots")

        logger.info(
            "Deleting lot: %s (%s shares of %s)",
            lot_id,
            lot.current_quantity,
            lot.ticker,
        )
        db.delete(lot)
        db.flush()

    # --- Batch ---

    @staticmethod
    def apply_lot_batch(
        db: Session,
        account_id: str,
        security_id: str,
        updates: list[LotBatchUpdate] | None = None,
        creates: list[LotBatchCreate] | None = None,
    ) -> list[HoldingLot]:
        """Apply a batch of lot updates and creates atomically.

        Validates that updated lots belong to the specified account/security.
        Returns all open lots for the security after the batch is applied.
        """
        updates = updates or []
        creates = creates or []

        for update in updates:
            lot = db.query(HoldingLot).filter_by(id=update.id).first()
            if not lot:
                raise ValueError(f"Lot not found: {update.id}")
            if lot.account_id != account_id or lot.security_id != security_id:
                raise ValueError(
                    f"Lot {update.id} does not belong to account "
                    f"{account_id} / security {security_id}"
                )
            update_data = HoldingLotUpdate(
                acquisition_date=update.acquisition_date,
                cost_basis_per_unit=update.cost_basis_per_unit,
                quantity=update.quantity,
            )
            LotLedgerService.update_lot(db, update.id, update_data)

        for create in creates:
            create_data = HoldingLotCreate(
                ticker=create.ticker,
                acquisition_date=create.acquisition_date,
                cost_basis_per_unit=create.cost_basis_per_unit,
                quantity=create.quantity,
            )
            LotLedgerService.create_lot(db, account_id, create_data)

        return LotLedgerService.get_lots_for_security(
            db, account_id, security_id, include_closed=False
        )

    # --- Queries ---

    @staticmethod
    def get_lots_for_account(
        db: Session, account_id: str, include_closed: bool = False
    ) -> list[HoldingLot]:
        """Get all lots for an account, ordered by acquisition date."""
        query = (
            db.query(HoldingLot)
            .options(joinedload(HoldingLot.security), joinedload(HoldingLot.disposals))
            .filter_by(account_id=account_id)
        )
        if not include_closed:
            query = query.filter_by(is_closed=False)
        return query.order_by(HoldingLot.acquisition_date.asc()).all()

    @staticmethod
    def get_lots_for_security(
        db: Session,
        account_id: str,
        security_id: str,
        include_closed: bool = False,
    ) -> list[HoldingLot]:
        """Get lots for a specific security in an account."""
        query = (
            db.query(HoldingLot)
            .options(joinedload(HoldingLot.security), joinedload(HoldingLot.disposals))
            .filter_by(account_id=account_id, security_id=security_id)
        )
        if not include_closed:
            query = query.filter_by(is_closed=False)
        return query.order_by(HoldingLot.acquisition_date.asc()).all()

    # --- Aggregation ---

    @staticmethod
    def get_lot_summary(
        db: Session,
        account_id: str,
        security_id: str,
        market_price: Decimal | None = None,
        total_quantity: Decimal | None = None,
    ) -> dict:
        """Compute an aggregated lot summary for a security.

        Args:
            db: Database session
            account_id: Account ID
            security_id: Security ID
            market_price: Current market price for unrealized gain/loss
            total_quantity: Total holding quantity for lot coverage calc

        Returns:
            Dict matching LotSummaryResponse fields.
        """
        security = db.query(Security).filter_by(id=security_id).first()
        lots = LotLedgerService.get_lots_for_security(
            db, account_id, security_id, include_closed=False
        )

        lotted_quantity = sum(
            (lot.current_quantity for lot in lots), Decimal("0")
        )
        total_cost_basis = sum(
            (lot.cost_basis_per_unit * lot.current_quantity for lot in lots),
            Decimal("0"),
        )

        # Unrealized gain/loss (requires market price)
        unrealized_gain_loss = None
        if market_price is not None and lotted_quantity > 0:
            market_value = market_price * lotted_quantity
            unrealized_gain_loss = market_value - total_cost_basis

        # Realized gain/loss from disposals
        disposals = (
            db.query(LotDisposal)
            .filter_by(account_id=account_id, security_id=security_id)
            .all()
        )
        realized_gain_loss = Decimal("0")
        for disposal in disposals:
            lot = disposal.holding_lot
            gain = (
                disposal.proceeds_per_unit - lot.cost_basis_per_unit
            ) * disposal.quantity
            realized_gain_loss += gain

        # Lot coverage
        lot_coverage = None
        if total_quantity is not None and total_quantity > 0:
            lot_coverage = lotted_quantity / total_quantity

        return {
            "security_id": security_id,
            "ticker": security.ticker if security else "",
            "security_name": security.name if security else None,
            "total_quantity": total_quantity,
            "lotted_quantity": lotted_quantity,
            "lot_count": len(lots),
            "total_cost_basis": total_cost_basis if lots else None,
            "unrealized_gain_loss": unrealized_gain_loss,
            "realized_gain_loss": realized_gain_loss,
            "lot_coverage": lot_coverage,
        }

    @staticmethod
    def get_lot_summaries_for_account(
        db: Session,
        account_id: str,
        market_prices: dict[str, Decimal] | None = None,
        total_quantities: dict[str, Decimal] | None = None,
    ) -> dict[str, dict]:
        """Get lot summaries grouped by security for an account.

        Args:
            db: Database session
            account_id: Account ID
            market_prices: Map of security_id -> market price
            total_quantities: Map of security_id -> total holding quantity

        Returns:
            Dict of security_id -> lot summary dict.
        """
        market_prices = market_prices or {}
        total_quantities = total_quantities or {}

        lots = LotLedgerService.get_lots_for_account(
            db, account_id, include_closed=False
        )

        # Collect unique security IDs
        security_ids = {lot.security_id for lot in lots}

        result = {}
        for security_id in security_ids:
            result[security_id] = LotLedgerService.get_lot_summary(
                db,
                account_id,
                security_id,
                market_price=market_prices.get(security_id),
                total_quantity=total_quantities.get(security_id),
            )

        return result

    # --- Disposal ---

    @staticmethod
    def reassign_disposals(
        db: Session,
        account_id: str,
        disposal_group_id: str,
        reassign_data: DisposalReassignRequest,
    ) -> list[LotDisposal]:
        """Reassign a disposal group to different lots.

        Validates that total reassigned quantity matches the original.
        Reverses old disposals (restoring lot quantities), deletes them,
        and creates new disposals with preserved metadata.
        """
        # Load existing disposals for this group
        old_disposals = (
            db.query(LotDisposal)
            .filter_by(
                account_id=account_id, disposal_group_id=disposal_group_id
            )
            .all()
        )
        if not old_disposals:
            raise ValueError(
                f"No disposals found for group: {disposal_group_id}"
            )

        # Validate total quantity matches
        old_total = sum(d.quantity for d in old_disposals)
        new_total = sum(a.quantity for a in reassign_data.assignments)
        if old_total != new_total:
            raise ValueError(
                f"Reassignment quantity ({new_total}) does not match "
                f"original ({old_total})"
            )

        # Preserve metadata from original disposals
        disposal_date = old_disposals[0].disposal_date
        proceeds_per_unit = old_disposals[0].proceeds_per_unit
        source = old_disposals[0].source
        security_id = old_disposals[0].security_id

        # Validate target lots
        for assignment in reassign_data.assignments:
            lot = db.query(HoldingLot).filter_by(id=assignment.lot_id).first()
            if not lot:
                raise ValueError(f"Lot not found: {assignment.lot_id}")
            if lot.account_id != account_id:
                raise ValueError(
                    f"Lot {assignment.lot_id} does not belong to "
                    f"account {account_id}"
                )
            if lot.security_id != security_id:
                raise ValueError(
                    f"Lot {assignment.lot_id} does not belong to "
                    f"security {security_id}"
                )

        # Reverse old disposals — restore lot quantities
        for disposal in old_disposals:
            lot = disposal.holding_lot
            lot.current_quantity += disposal.quantity
            lot.is_closed = False
            db.delete(disposal)

        db.flush()

        # Create new disposals
        new_group_id = generate_uuid()
        new_disposals = []
        for assignment in reassign_data.assignments:
            lot = db.query(HoldingLot).filter_by(id=assignment.lot_id).first()

            disposal = LotDisposal(
                holding_lot_id=assignment.lot_id,
                account_id=account_id,
                security_id=security_id,
                disposal_date=disposal_date,
                quantity=assignment.quantity,
                proceeds_per_unit=proceeds_per_unit,
                source=source,
                disposal_group_id=new_group_id,
            )
            db.add(disposal)

            # Update lot quantities
            lot.current_quantity -= assignment.quantity
            if lot.current_quantity == 0:
                lot.is_closed = True

            new_disposals.append(disposal)

        db.flush()
        logger.info(
            "Reassigned disposal group %s -> %s (%s assignments)",
            disposal_group_id,
            new_group_id,
            len(reassign_data.assignments),
        )
        return new_disposals
