"""Asset Classes API endpoints."""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.helpers import get_or_404
from database import get_db
from models import AssetClass
from schemas.account import (
    AssetClassCreate,
    AssetClassListResponse,
    AssetClassResponse,
    AssetClassUpdate,
    AssetClassWithCounts,
    AssetTypeHoldingResponse,
    AssetTypeHoldingsDetail,
)
from services.asset_type_service import AssetTypeService
from services.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/asset-types", tags=["asset-types"])
service = AssetTypeService()


@router.get("", response_model=AssetClassListResponse)
def list_asset_types(db: Session = Depends(get_db)):
    """
    List all asset types with total target percentage.

    Returns list of asset types and the sum of all target percentages.
    """
    items = service.list_all(db)
    total = service.get_total_target_percent(db)
    return {"items": items, "total_target_percent": total}


@router.post("", response_model=AssetClassResponse, status_code=201)
def create_asset_type(
    asset_type_data: AssetClassCreate, db: Session = Depends(get_db)
):
    """
    Create a new asset type.

    Requires name and color. Returns the created asset type.
    """
    return service.create(db, asset_type_data.name, asset_type_data.color)


@router.get("/{asset_type_id}", response_model=AssetClassWithCounts)
def get_asset_type(asset_type_id: str, db: Session = Depends(get_db)):
    """
    Get a specific asset type by ID with assignment counts.

    Returns the asset type along with counts of securities and accounts
    assigned to it.
    """
    asset_type = service.get_by_id(db, asset_type_id)
    if not asset_type:
        raise HTTPException(status_code=404, detail="Asset type not found")

    counts = service.get_assignment_counts(db, asset_type_id)

    return {
        **asset_type.__dict__,
        "security_count": counts["security_count"],
        "account_count": counts["account_count"],
    }


@router.patch("/{asset_type_id}", response_model=AssetClassResponse)
def update_asset_type(
    asset_type_id: str,
    update_data: AssetClassUpdate,
    db: Session = Depends(get_db),
):
    """
    Update an asset type.

    Can update name, color, and/or target_percent.
    """
    return service.update(
        db,
        asset_type_id,
        name=update_data.name,
        color=update_data.color,
        target_percent=update_data.target_percent,
    )


@router.delete("/{asset_type_id}", status_code=204)
def delete_asset_type(asset_type_id: str, db: Session = Depends(get_db)):
    """
    Delete an asset type.

    Fails if the asset type has any securities or accounts assigned to it.
    """
    service.delete(db, asset_type_id)


@router.get("/{asset_type_id}/holdings", response_model=AssetTypeHoldingsDetail)
def get_asset_type_holdings(
    asset_type_id: str,
    db: Session = Depends(get_db),
):
    """
    Get all holdings classified under a specific asset type.

    For asset_type_id="unassigned", returns holdings with no classification.
    """
    # Validate asset type exists (unless "unassigned")
    if asset_type_id != "unassigned":
        asset_type = get_or_404(db, AssetClass, asset_type_id, "Asset type not found")
        type_name = asset_type.name
        type_color = asset_type.color
    else:
        type_name = "Unknown"
        type_color = "#9CA3AF"

    portfolio_service = PortfolioService()
    holdings_data = portfolio_service.get_holdings_for_asset_type(
        db, asset_type_id, allocation_only=True
    )

    holdings = [
        AssetTypeHoldingResponse(
            holding_id=h["holding_id"],
            account_id=h["account_id"],
            account_name=h["account_name"],
            ticker=h["ticker"],
            security_name=h["security_name"],
            market_value=h["market_value"],
        )
        for h in holdings_data
    ]

    total_value = sum((h.market_value for h in holdings), Decimal("0.00"))

    return AssetTypeHoldingsDetail(
        asset_type_id=asset_type_id,
        asset_type_name=type_name,
        asset_type_color=type_color,
        total_value=total_value,
        holdings=holdings,
    )
