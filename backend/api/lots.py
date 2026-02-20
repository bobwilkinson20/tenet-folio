"""Lot management API endpoints."""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.helpers import get_or_404
from database import get_db
from models import Account, HoldingLot, LotDisposal, Security
from schemas.lot import (
    DisposalReassignRequest,
    HoldingLotCreate,
    HoldingLotResponse,
    HoldingLotUpdate,
    LotBatchRequest,
    LotDisposalResponse,
    LotSummaryResponse,
)
from services.lot_ledger_service import LotLedgerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["lots"])


def _disposal_response_dict(disposal: LotDisposal, lot: HoldingLot) -> dict:
    """Build a LotDisposalResponse-compatible dict with realized gain/loss."""
    realized = (disposal.proceeds_per_unit - lot.cost_basis_per_unit) * disposal.quantity
    return {
        "id": disposal.id,
        "holding_lot_id": disposal.holding_lot_id,
        "account_id": disposal.account_id,
        "security_id": disposal.security_id,
        "disposal_date": disposal.disposal_date,
        "quantity": disposal.quantity,
        "proceeds_per_unit": disposal.proceeds_per_unit,
        "realized_gain_loss": realized,
        "source": disposal.source,
        "activity_id": disposal.activity_id,
        "disposal_group_id": disposal.disposal_group_id,
        "created_at": disposal.created_at,
    }


def _lot_response_dict(lot: HoldingLot, market_price: Decimal | None = None) -> dict:
    """Enrich a HoldingLot with computed fields for the API response."""
    total_cost_basis = lot.cost_basis_per_unit * lot.current_quantity

    unrealized_gain_loss = None
    unrealized_gain_loss_percent = None
    if market_price is not None:
        market_value = market_price * lot.current_quantity
        unrealized_gain_loss = market_value - total_cost_basis
        if total_cost_basis != 0:
            unrealized_gain_loss_percent = (
                unrealized_gain_loss / total_cost_basis
            ) * Decimal("100")

    return {
        "id": lot.id,
        "account_id": lot.account_id,
        "security_id": lot.security_id,
        "ticker": lot.ticker,
        "acquisition_date": lot.acquisition_date,
        "cost_basis_per_unit": lot.cost_basis_per_unit,
        "original_quantity": lot.original_quantity,
        "current_quantity": lot.current_quantity,
        "is_closed": lot.is_closed,
        "source": lot.source,
        "activity_id": lot.activity_id,
        "created_at": lot.created_at,
        "updated_at": lot.updated_at,
        "total_cost_basis": total_cost_basis,
        "unrealized_gain_loss": unrealized_gain_loss,
        "unrealized_gain_loss_percent": unrealized_gain_loss_percent,
        "security_name": lot.security.name if lot.security else None,
        "disposals": [_disposal_response_dict(d, lot) for d in lot.disposals],
    }


@router.get("/{account_id}/lots", response_model=list[HoldingLotResponse])
def get_account_lots(
    account_id: str,
    include_closed: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Get all lots for an account."""
    get_or_404(db, Account, account_id, "Account not found")
    lots = LotLedgerService.get_lots_for_account(db, account_id, include_closed)
    return [_lot_response_dict(lot) for lot in lots]


@router.get("/{account_id}/lots/summary", response_model=list[LotSummaryResponse])
def get_account_lot_summaries(
    account_id: str,
    db: Session = Depends(get_db),
):
    """Get aggregated lot summaries grouped by security for an account."""
    get_or_404(db, Account, account_id, "Account not found")
    summaries = LotLedgerService.get_lot_summaries_for_account(db, account_id)
    return list(summaries.values())


@router.get(
    "/{account_id}/lots/by-security/{security_id}",
    response_model=list[HoldingLotResponse],
)
def get_lots_by_security(
    account_id: str,
    security_id: str,
    db: Session = Depends(get_db),
):
    """Get lots for a specific security in an account."""
    get_or_404(db, Account, account_id, "Account not found")
    get_or_404(db, Security, security_id, "Security not found")
    lots = LotLedgerService.get_lots_for_security(db, account_id, security_id)
    return [_lot_response_dict(lot) for lot in lots]


@router.put(
    "/{account_id}/lots/by-security/{security_id}/batch",
    response_model=list[HoldingLotResponse],
)
def batch_save_lots(
    account_id: str,
    security_id: str,
    batch_data: LotBatchRequest,
    db: Session = Depends(get_db),
):
    """Batch create/update lots for a security atomically."""
    get_or_404(db, Account, account_id, "Account not found")
    get_or_404(db, Security, security_id, "Security not found")
    try:
        lots = LotLedgerService.apply_lot_batch(
            db,
            account_id,
            security_id,
            updates=batch_data.updates,
            creates=batch_data.creates,
        )
        db.commit()
        for lot in lots:
            db.refresh(lot)
        return [_lot_response_dict(lot) for lot in lots]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{account_id}/lots", response_model=HoldingLotResponse, status_code=201)
def create_lot(
    account_id: str,
    lot_data: HoldingLotCreate,
    db: Session = Depends(get_db),
):
    """Create a new manual lot."""
    get_or_404(db, Account, account_id, "Account not found")
    try:
        lot = LotLedgerService.create_lot(db, account_id, lot_data)
        db.commit()
        db.refresh(lot)
        return _lot_response_dict(lot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{account_id}/lots/{lot_id}", response_model=HoldingLotResponse)
def update_lot(
    account_id: str,
    lot_id: str,
    lot_data: HoldingLotUpdate,
    db: Session = Depends(get_db),
):
    """Update a lot."""
    get_or_404(db, Account, account_id, "Account not found")

    # Verify lot belongs to account
    lot = db.query(HoldingLot).filter_by(id=lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    if lot.account_id != account_id:
        raise HTTPException(status_code=404, detail="Lot not found")

    try:
        lot = LotLedgerService.update_lot(db, lot_id, lot_data)
        db.commit()
        db.refresh(lot)
        return _lot_response_dict(lot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{account_id}/lots/{lot_id}", status_code=204)
def delete_lot(
    account_id: str,
    lot_id: str,
    db: Session = Depends(get_db),
):
    """Delete a lot."""
    get_or_404(db, Account, account_id, "Account not found")

    # Verify lot belongs to account
    lot = db.query(HoldingLot).filter_by(id=lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    if lot.account_id != account_id:
        raise HTTPException(status_code=404, detail="Lot not found")

    try:
        LotLedgerService.delete_lot(db, lot_id)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put(
    "/{account_id}/lots/disposals/{disposal_group_id}/reassign",
    response_model=list[LotDisposalResponse],
)
def reassign_disposals(
    account_id: str,
    disposal_group_id: str,
    reassign_data: DisposalReassignRequest,
    db: Session = Depends(get_db),
):
    """Reassign a disposal group to different lots."""
    get_or_404(db, Account, account_id, "Account not found")
    try:
        disposals = LotLedgerService.reassign_disposals(
            db, account_id, disposal_group_id, reassign_data
        )
        db.commit()
        for d in disposals:
            db.refresh(d)
        return [_disposal_response_dict(d, d.holding_lot) for d in disposals]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
