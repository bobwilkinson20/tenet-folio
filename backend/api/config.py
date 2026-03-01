"""Configuration info endpoint."""

from fastapi import APIRouter

from services.credential_manager import ACTIVE_PROFILE

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/profile")
def get_profile():
    """Return the active profile name (null when no profile is set)."""
    return {"profile": ACTIVE_PROFILE}
