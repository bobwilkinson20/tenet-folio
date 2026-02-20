"""Preference service - manages user preference CRUD operations."""

import json
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.user_preference import UserPreference

logger = logging.getLogger(__name__)


class PreferenceService:
    """Service for managing user preferences as a key-value store."""

    @staticmethod
    def get_all(db: Session) -> dict[str, Any]:
        """Get all preferences as a {key: parsed_value} dict."""
        prefs = db.query(UserPreference).all()
        return {p.key: json.loads(p.value) for p in prefs}

    @staticmethod
    def get(db: Session, key: str) -> Any | None:
        """Get a single preference value by key, or None if not found."""
        pref = PreferenceService.get_record(db, key)
        if pref is None:
            return None
        return json.loads(pref.value)

    @staticmethod
    def get_record(db: Session, key: str) -> UserPreference | None:
        """Get the full UserPreference record by key, or None if not found."""
        return db.query(UserPreference).filter(UserPreference.key == key).first()

    @staticmethod
    def set(db: Session, key: str, value: Any) -> UserPreference:
        """Create or update a preference. Returns the UserPreference record."""
        pref = db.query(UserPreference).filter(UserPreference.key == key).first()
        serialized = json.dumps(value)

        if pref is None:
            pref = UserPreference(key=key, value=serialized)
            db.add(pref)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                pref = db.query(UserPreference).filter(
                    UserPreference.key == key
                ).first()
                pref.value = serialized
                db.commit()
                logger.info("Updated preference (concurrent insert): %s", key)
            else:
                logger.info("Created preference: %s", key)
        else:
            pref.value = serialized
            db.commit()
            logger.info("Updated preference: %s", key)

        db.refresh(pref)
        return pref

    @staticmethod
    def delete(db: Session, key: str) -> bool:
        """Delete a preference by key. Returns True if deleted, False if not found."""
        pref = db.query(UserPreference).filter(UserPreference.key == key).first()
        if pref is None:
            return False
        db.delete(pref)
        db.commit()
        logger.info("Deleted preference: %s", key)
        return True
