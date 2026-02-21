"""Plaid Link API endpoints.

Provides the server-side endpoints for the Plaid Link browser-based
authentication flow: creating link tokens, exchanging public tokens,
and managing linked institutions (PlaidItems).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from integrations.plaid_client import PlaidClient
from models.plaid_item import PlaidItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plaid", tags=["plaid"])


def _get_plaid_client() -> PlaidClient:
    """Dependency for injecting the Plaid client (overridable in tests)."""
    return PlaidClient()


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeTokenRequest(BaseModel):
    public_token: str
    institution_id: str | None = None
    institution_name: str | None = None


class ExchangeTokenResponse(BaseModel):
    item_id: str
    institution_name: str | None = None


class PlaidItemResponse(BaseModel):
    id: str
    item_id: str
    institution_id: str | None = None
    institution_name: str | None = None
    created_at: str | None = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/link-token", response_model=LinkTokenResponse)
def create_link_token(
    client: PlaidClient = Depends(_get_plaid_client),
):
    """Create a Plaid Link token for the frontend."""
    if not client.is_configured():
        raise HTTPException(status_code=400, detail="Plaid is not configured")

    try:
        link_token = client.create_link_token()
        return LinkTokenResponse(link_token=link_token)
    except Exception as e:
        error_detail = str(e)
        # Surface actionable hint for the most common error
        if "INVALID_API_KEYS" in error_detail:
            hint = (
                "Plaid rejected the credentials. Check that PLAID_ENVIRONMENT "
                "matches your keys (sandbox or production). "
                "Each environment has different secrets."
            )
            logger.error("Plaid INVALID_API_KEYS: %s", hint)
            raise HTTPException(status_code=400, detail=hint)
        logger.error("Failed to create Plaid link token: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create link token")


@router.post("/exchange-token", response_model=ExchangeTokenResponse)
def exchange_token(
    body: ExchangeTokenRequest,
    db: Session = Depends(get_db),
    client: PlaidClient = Depends(_get_plaid_client),
):
    """Exchange a Plaid Link public_token and store the resulting Item."""
    if not client.is_configured():
        raise HTTPException(status_code=400, detail="Plaid is not configured")

    try:
        result = client.exchange_public_token(body.public_token)
    except Exception as e:
        logger.error("Failed to exchange Plaid token: %s", e)
        raise HTTPException(status_code=500, detail="Failed to exchange token")

    item_id = result["item_id"]
    access_token = result["access_token"]

    # Upsert: update existing item or create new one
    existing = db.query(PlaidItem).filter(PlaidItem.item_id == item_id).first()
    if existing:
        existing.access_token = access_token
        if body.institution_id:
            existing.institution_id = body.institution_id
        if body.institution_name:
            existing.institution_name = body.institution_name
        logger.info("Updated PlaidItem %s", item_id)
    else:
        new_item = PlaidItem(
            item_id=item_id,
            access_token=access_token,
            institution_id=body.institution_id,
            institution_name=body.institution_name,
        )
        db.add(new_item)
        logger.info("Created PlaidItem %s for %s", item_id, body.institution_name)

    db.commit()

    return ExchangeTokenResponse(
        item_id=item_id,
        institution_name=body.institution_name,
    )


@router.get("/items", response_model=list[PlaidItemResponse])
def list_items(db: Session = Depends(get_db)):
    """List all linked Plaid Items."""
    items = db.query(PlaidItem).order_by(PlaidItem.created_at.desc()).all()
    return [
        PlaidItemResponse(
            id=item.id,
            item_id=item.item_id,
            institution_id=item.institution_id,
            institution_name=item.institution_name,
            created_at=item.created_at.isoformat() if item.created_at else None,
        )
        for item in items
    ]


@router.delete("/items/{item_id}")
def remove_item(
    item_id: str,
    db: Session = Depends(get_db),
    client: PlaidClient = Depends(_get_plaid_client),
):
    """Remove a linked Plaid Item (revokes token with Plaid, then deletes locally)."""
    item = db.query(PlaidItem).filter(PlaidItem.item_id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")

    # Revoke the access token with Plaid; proceed with local delete even if this fails
    try:
        client.remove_item(item.access_token)
    except Exception as e:
        logger.warning("Failed to remove Plaid item remotely (removing locally anyway): %s", e)

    db.delete(item)
    db.commit()
    logger.info("Deleted PlaidItem %s", item_id)
    return {"status": "ok", "item_id": item_id}
