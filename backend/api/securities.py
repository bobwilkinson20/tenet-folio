"""Securities API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.helpers import get_or_404, security_response_dict
from database import get_db
from models import Security
from utils.ticker import ZERO_BALANCE_TICKER
from schemas.account import (
    SecurityResponse,
    SecurityUpdate,
    SecurityWithTypeResponse,
    UnassignedResponse,
)

router = APIRouter(prefix="/api/securities", tags=["securities"])


@router.get("", response_model=list[SecurityWithTypeResponse])
def list_securities(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    unassigned_only: bool = Query(False),
):
    """
    List all securities with their asset type information.

    Args:
        search: Optional search term to filter by ticker or name
        unassigned_only: If true, only show securities without an assigned type

    Returns:
        List of securities with asset type info
    """
    query = db.query(Security).filter(Security.ticker != ZERO_BALANCE_TICKER)

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Security.ticker.ilike(search_term)) | (Security.name.ilike(search_term))
        )

    # Apply unassigned filter
    if unassigned_only:
        query = query.filter(Security.manual_asset_class_id.is_(None))

    securities = query.order_by(Security.ticker).all()
    return [security_response_dict(sec) for sec in securities]


@router.get("/unassigned", response_model=UnassignedResponse)
def get_unassigned_securities(db: Session = Depends(get_db)):
    """
    Get count and list of securities without an assigned asset type.

    Returns:
        Count and list of unassigned securities
    """
    securities = (
        db.query(Security)
        .filter(
            Security.manual_asset_class_id.is_(None),
            Security.ticker != ZERO_BALANCE_TICKER,
        )
        .order_by(Security.ticker)
        .all()
    )

    items = [security_response_dict(sec) for sec in securities]
    return {"count": len(items), "items": items}


@router.patch("/{security_id}", response_model=SecurityResponse)
def update_security_type(
    security_id: str, update_data: SecurityUpdate, db: Session = Depends(get_db)
):
    """
    Update a security's asset type assignment.

    Can set manual_asset_class_id to assign a type, or set to null to clear.

    Args:
        security_id: The security ID
        update_data: Update data (manual_asset_class_id)

    Returns:
        Updated security
    """
    security = get_or_404(db, Security, security_id, "Security not found")

    # Update only the fields that are provided
    if update_data.manual_asset_class_id is not None or "manual_asset_class_id" in update_data.model_fields_set:
        security.manual_asset_class_id = update_data.manual_asset_class_id

    if update_data.name is not None:
        security.name = update_data.name

    db.commit()
    db.refresh(security)

    return security
