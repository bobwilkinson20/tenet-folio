"""Preferences API endpoints."""

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.user_preference import UserPreference
from schemas.preference import PreferenceResponse, PreferenceSet
from services.preference_service import PreferenceService

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

# Namespaced key pattern: one or more dot-separated segments of alphanumerics/underscores,
# starting with a lowercase letter. e.g. "accounts.hideInactive", "ui.theme"
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")
_KEY_MAX_LENGTH = 128


def _validate_key(key: str) -> None:
    """Validate preference key format. Raises HTTPException on invalid keys."""
    if len(key) > _KEY_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Preference key must be at most {_KEY_MAX_LENGTH} characters",
        )
    if not _KEY_PATTERN.match(key):
        raise HTTPException(
            status_code=422,
            detail="Preference key must be a dot-namespaced identifier "
            "(e.g. 'accounts.hideInactive')",
        )


def _to_response(pref: UserPreference) -> PreferenceResponse:
    """Convert a UserPreference record to a PreferenceResponse."""
    return PreferenceResponse(
        key=pref.key,
        value=json.loads(pref.value),
        updated_at=pref.updated_at,
    )


@router.get("", response_model=dict[str, Any])
def list_preferences(db: Session = Depends(get_db)):
    """Get all preferences as a flat {key: value} dict."""
    return PreferenceService.get_all(db)


@router.get("/{key:path}", response_model=PreferenceResponse)
def get_preference(key: str, db: Session = Depends(get_db)):
    """Get a single preference with metadata."""
    _validate_key(key)
    pref = PreferenceService.get_record(db, key)
    if pref is None:
        raise HTTPException(status_code=404, detail=f"Preference '{key}' not found")
    return _to_response(pref)


@router.put("/{key:path}", response_model=PreferenceResponse)
def set_preference(key: str, body: PreferenceSet, db: Session = Depends(get_db)):
    """Create or update a preference (idempotent upsert)."""
    _validate_key(key)
    pref = PreferenceService.set(db, key, body.value)
    return _to_response(pref)


@router.delete("/{key:path}", status_code=204)
def delete_preference(key: str, db: Session = Depends(get_db)):
    """Delete a preference by key."""
    _validate_key(key)
    deleted = PreferenceService.delete(db, key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Preference '{key}' not found")
