"""Integration tests for preferences API endpoints."""


class TestGetAllPreferences:
    """Tests for GET /api/preferences."""

    def test_get_all_empty(self, client):
        """Returns empty dict when no preferences exist."""
        response = client.get("/api/preferences")
        assert response.status_code == 200
        assert response.json() == {}

    def test_get_all_returns_multiple(self, client):
        """Returns all stored preferences."""
        client.put("/api/preferences/test.key1", json={"value": "string_val"})
        client.put("/api/preferences/test.key2", json={"value": True})

        response = client.get("/api/preferences")
        assert response.status_code == 200
        data = response.json()
        assert data["test.key1"] == "string_val"
        assert data["test.key2"] is True


class TestGetPreference:
    """Tests for GET /api/preferences/{key}."""

    def test_get_single_exists(self, client):
        """Returns preference with metadata."""
        client.put("/api/preferences/my.key", json={"value": "hello"})

        response = client.get("/api/preferences/my.key")
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "my.key"
        assert data["value"] == "hello"
        assert "updated_at" in data

    def test_get_single_not_found(self, client):
        """Returns 404 for missing key."""
        response = client.get("/api/preferences/accounts.nonexistent")
        assert response.status_code == 404


class TestPutPreference:
    """Tests for PUT /api/preferences/{key}."""

    def test_put_creates(self, client):
        """Creates a new preference."""
        response = client.put("/api/preferences/new.key", json={"value": 42})
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "new.key"
        assert data["value"] == 42

    def test_put_updates(self, client):
        """Updates an existing preference."""
        client.put("/api/preferences/test.key", json={"value": "original"})
        response = client.put("/api/preferences/test.key", json={"value": "updated"})
        assert response.status_code == 200
        assert response.json()["value"] == "updated"

    def test_put_boolean(self, client):
        """Stores and returns boolean values."""
        response = client.put("/api/preferences/test.flag", json={"value": True})
        assert response.status_code == 200
        assert response.json()["value"] is True

    def test_put_string(self, client):
        """Stores and returns string values."""
        response = client.put("/api/preferences/test.name", json={"value": "hello"})
        assert response.status_code == 200
        assert response.json()["value"] == "hello"

    def test_put_object(self, client):
        """Stores and returns JSON object values."""
        obj = {"nested": {"key": "value"}}
        response = client.put("/api/preferences/test.config", json={"value": obj})
        assert response.status_code == 200
        assert response.json()["value"] == obj

    def test_put_null(self, client):
        """Stores and returns null values."""
        response = client.put("/api/preferences/test.empty", json={"value": None})
        assert response.status_code == 200
        assert response.json()["value"] is None


class TestDeletePreference:
    """Tests for DELETE /api/preferences/{key}."""

    def test_delete_existing(self, client):
        """Returns 204 and removes the preference."""
        client.put("/api/preferences/test.toDelete", json={"value": "val"})
        response = client.delete("/api/preferences/test.toDelete")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get("/api/preferences/test.toDelete")
        assert response.status_code == 404

    def test_delete_not_found(self, client):
        """Returns 404 for missing key."""
        response = client.delete("/api/preferences/accounts.nonexistent")
        assert response.status_code == 404


class TestKeyValidation:
    """Tests for preference key format validation."""

    def test_rejects_empty_key(self, client):
        """Rejects empty string key (hits list endpoint instead)."""
        # An empty key routes to GET /api/preferences which is the list endpoint
        # so we test with PUT which would be /api/preferences/
        response = client.put("/api/preferences/", json={"value": "x"})
        # FastAPI returns 307 redirect or 405; either way it's not 200
        assert response.status_code != 200

    def test_rejects_single_segment_key(self, client):
        """Rejects keys without a dot namespace."""
        response = client.put("/api/preferences/nodot", json={"value": "x"})
        assert response.status_code == 422

    def test_rejects_key_starting_with_uppercase(self, client):
        """Rejects keys where the first segment starts with uppercase."""
        response = client.put("/api/preferences/Accounts.key", json={"value": "x"})
        assert response.status_code == 422

    def test_rejects_key_starting_with_number(self, client):
        """Rejects keys where the first segment starts with a number."""
        response = client.put("/api/preferences/1accounts.key", json={"value": "x"})
        assert response.status_code == 422

    def test_rejects_key_with_spaces(self, client):
        """Rejects keys containing spaces."""
        response = client.put("/api/preferences/my.bad key", json={"value": "x"})
        assert response.status_code == 422

    def test_rejects_key_with_special_chars(self, client):
        """Rejects keys with special characters."""
        response = client.put("/api/preferences/my.key!", json={"value": "x"})
        assert response.status_code == 422

    def test_rejects_overly_long_key(self, client):
        """Rejects keys exceeding max length."""
        long_key = "a" + ".b" * 100  # 201 chars
        response = client.put(f"/api/preferences/{long_key}", json={"value": "x"})
        assert response.status_code == 422

    def test_accepts_valid_namespaced_key(self, client):
        """Accepts properly formatted namespaced keys."""
        response = client.put(
            "/api/preferences/accounts.hideInactive", json={"value": True}
        )
        assert response.status_code == 200

    def test_accepts_multi_segment_key(self, client):
        """Accepts keys with multiple dot-separated segments."""
        response = client.put(
            "/api/preferences/ui.accounts.sortOrder", json={"value": "asc"}
        )
        assert response.status_code == 200

    def test_accepts_underscores_in_segments(self, client):
        """Accepts underscores in key segments."""
        response = client.put(
            "/api/preferences/accounts.hide_inactive", json={"value": True}
        )
        assert response.status_code == 200

    def test_validation_applies_to_get(self, client):
        """Key validation also applies to GET requests."""
        response = client.get("/api/preferences/invalid!")
        assert response.status_code == 422

    def test_validation_applies_to_delete(self, client):
        """Key validation also applies to DELETE requests."""
        response = client.delete("/api/preferences/invalid!")
        assert response.status_code == 422
