"""Shared API helpers for route handlers.

Common query patterns and response builders used across multiple route files.
"""

from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import Base
from models import AccountSnapshot, Holding, Security, SyncSession

T = TypeVar("T", bound=Base)


def get_or_404(db: Session, model: type[T], entity_id: str, detail: str = "Not found") -> T:
    """Fetch a single entity by primary key or raise 404.

    Args:
        db: Database session.
        model: SQLAlchemy model class.
        entity_id: Primary key value.
        detail: Error message for the 404 response.

    Returns:
        The entity instance.

    Raises:
        HTTPException: 404 if the entity doesn't exist.
    """
    entity = db.query(model).filter(model.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail=detail)
    return entity


def get_latest_account_snapshot(db: Session, account_id: str) -> AccountSnapshot | None:
    """Return the most recent AccountSnapshot for an account.

    Args:
        db: Database session.
        account_id: The account to look up.

    Returns:
        The latest AccountSnapshot, or None if none exist.
    """
    return (
        db.query(AccountSnapshot)
        .join(SyncSession)
        .filter(AccountSnapshot.account_id == account_id)
        .order_by(SyncSession.timestamp.desc())
        .limit(1)
        .first()
    )


def holding_response_dict(holding: Holding) -> dict:
    """Build a HoldingResponse-compatible dict from a Holding.

    Args:
        holding: A Holding instance with its security relationship loaded.

    Returns:
        Dict matching the HoldingResponse schema.
    """
    return {
        "id": holding.id,
        "account_snapshot_id": holding.account_snapshot_id,
        "security_id": holding.security_id,
        "ticker": holding.ticker,
        "quantity": holding.quantity,
        "snapshot_price": holding.snapshot_price,
        "snapshot_value": holding.snapshot_value,
        "created_at": holding.created_at,
        "security_name": holding.security.name if holding.security else None,
    }


def security_response_dict(sec: Security) -> dict:
    """Build a SecurityWithTypeResponse-compatible dict from a Security.

    Args:
        sec: A Security instance with its manual_asset_class relationship loaded.

    Returns:
        Dict matching the SecurityWithTypeResponse schema.
    """
    result = {
        "id": sec.id,
        "ticker": sec.ticker,
        "name": sec.name,
        "manual_asset_class_id": sec.manual_asset_class_id,
        "created_at": sec.created_at,
        "updated_at": sec.updated_at,
        "asset_type_id": None,
        "asset_type_name": None,
        "asset_type_color": None,
    }

    if sec.manual_asset_class_id and sec.manual_asset_class:
        result["asset_type_id"] = sec.manual_asset_class.id
        result["asset_type_name"] = sec.manual_asset_class.name
        result["asset_type_color"] = sec.manual_asset_class.color

    return result
