"""Tests for PreferenceService."""

from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

from models.user_preference import UserPreference
from services.preference_service import PreferenceService


class TestPreferenceServiceGetAll:
    """Tests for PreferenceService.get_all."""

    def test_get_all_empty(self, db):
        """Returns empty dict when no preferences exist."""
        result = PreferenceService.get_all(db)
        assert result == {}

    def test_get_all_returns_multiple(self, db):
        """Returns all stored preferences."""
        PreferenceService.set(db, "key1", "value1")
        PreferenceService.set(db, "key2", True)
        PreferenceService.set(db, "key3", 42)

        result = PreferenceService.get_all(db)
        assert result == {"key1": "value1", "key2": True, "key3": 42}


class TestPreferenceServiceGet:
    """Tests for PreferenceService.get."""

    def test_get_nonexistent(self, db):
        """Returns None for missing key."""
        result = PreferenceService.get(db, "nonexistent")
        assert result is None

    def test_get_boolean(self, db):
        """Gets a boolean preference."""
        PreferenceService.set(db, "flag", True)
        assert PreferenceService.get(db, "flag") is True

    def test_get_string(self, db):
        """Gets a string preference."""
        PreferenceService.set(db, "name", "hello")
        assert PreferenceService.get(db, "name") == "hello"

    def test_get_number(self, db):
        """Gets a numeric preference."""
        PreferenceService.set(db, "count", 42)
        assert PreferenceService.get(db, "count") == 42

    def test_get_json_object(self, db):
        """Gets a JSON object preference."""
        obj = {"nested": {"key": "value"}, "list": [1, 2, 3]}
        PreferenceService.set(db, "config", obj)
        assert PreferenceService.get(db, "config") == obj

    def test_get_null(self, db):
        """Gets a null preference (stored as JSON null)."""
        PreferenceService.set(db, "empty", None)
        assert PreferenceService.get(db, "empty") is None


class TestPreferenceServiceSet:
    """Tests for PreferenceService.set."""

    def test_set_creates_new(self, db):
        """Creates a new preference when key doesn't exist."""
        pref = PreferenceService.set(db, "new_key", "new_value")
        assert pref.key == "new_key"
        assert pref.id is not None
        assert pref.created_at is not None
        assert pref.updated_at is not None

    def test_set_updates_existing(self, db):
        """Updates value when key already exists."""
        PreferenceService.set(db, "key", "original")
        PreferenceService.set(db, "key", "updated")

        result = PreferenceService.get(db, "key")
        assert result == "updated"

    def test_set_preserves_id_on_update(self, db):
        """Keeps the same record ID when updating."""
        pref1 = PreferenceService.set(db, "key", "v1")
        pref2 = PreferenceService.set(db, "key", "v2")
        assert pref1.id == pref2.id

    def test_set_handles_concurrent_insert_race(self, db):
        """Recovers when a concurrent insert causes IntegrityError."""
        # Simulate: another request inserts "race_key" between our
        # SELECT (returns None) and our INSERT (commit raises IntegrityError).
        original_commit = db.commit
        call_count = 0

        def commit_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First commit (the insert attempt) — simulate race by
                # flushing, inserting a conflicting row, then raising.
                db.rollback()
                rival = UserPreference(key="race_key", value='"rival_value"')
                db.add(rival)
                original_commit()
                raise IntegrityError(
                    statement="INSERT INTO user_preferences",
                    params={},
                    orig=Exception("UNIQUE constraint failed"),
                )
            # Subsequent commits proceed normally.
            original_commit()

        with patch.object(db, "commit", side_effect=commit_side_effect):
            pref = PreferenceService.set(db, "race_key", "winner_value")

        assert pref.key == "race_key"
        assert PreferenceService.get(db, "race_key") == "winner_value"


class TestPreferenceServiceDelete:
    """Tests for PreferenceService.delete."""

    def test_delete_existing(self, db):
        """Returns True and removes the preference."""
        PreferenceService.set(db, "to_delete", "value")
        result = PreferenceService.delete(db, "to_delete")
        assert result is True
        assert PreferenceService.get(db, "to_delete") is None

    def test_delete_nonexistent(self, db):
        """Returns False when key doesn't exist."""
        result = PreferenceService.delete(db, "nonexistent")
        assert result is False
