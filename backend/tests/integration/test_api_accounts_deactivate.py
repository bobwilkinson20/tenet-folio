"""Integration tests for the POST /api/accounts/{id}/deactivate endpoint."""

from decimal import Decimal

from models import Account, DailyHoldingValue, SyncSession
from utils.ticker import ZERO_BALANCE_TICKER


def _make_account(db, *, provider="SimpleFIN", external_id="sf_1", is_active=True):
    account = Account(
        provider_name=provider,
        external_id=external_id,
        name=f"{provider} Test Account",
        is_active=is_active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def test_deactivate_account_returns_200(client, account):
    """POST /deactivate on an active account returns 200."""
    response = client.post(
        f"/api/accounts/{account.id}/deactivate",
        json={"create_closing_snapshot": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False
    assert data["deactivated_at"] is not None


def test_deactivate_account_with_closing_snapshot(client, db, account):
    """Deactivate with create_closing_snapshot=True creates DHV sentinel."""
    response = client.post(
        f"/api/accounts/{account.id}/deactivate",
        json={"create_closing_snapshot": True},
    )
    assert response.status_code == 200

    sentinel_dhv = (
        db.query(DailyHoldingValue)
        .filter_by(account_id=account.id)
        .first()
    )
    assert sentinel_dhv is not None
    assert sentinel_dhv.ticker == ZERO_BALANCE_TICKER
    assert sentinel_dhv.market_value == Decimal("0")


def test_deactivate_account_without_closing_snapshot(client, db, account):
    """Deactivate with create_closing_snapshot=False creates no DHV."""
    response = client.post(
        f"/api/accounts/{account.id}/deactivate",
        json={"create_closing_snapshot": False},
    )
    assert response.status_code == 200
    assert db.query(DailyHoldingValue).count() == 0
    assert db.query(SyncSession).count() == 0


def test_deactivate_account_with_superseded_by(client, db):
    """Deactivate with superseded_by_account_id links replacement account."""
    old = _make_account(db, provider="SimpleFIN", external_id="sf_1")
    new = _make_account(db, provider="Plaid", external_id="plaid_1")

    response = client.post(
        f"/api/accounts/{old.id}/deactivate",
        json={
            "create_closing_snapshot": False,
            "superseded_by_account_id": new.id,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["superseded_by_account_id"] == new.id
    assert data["superseded_by_name"] == new.name


def test_deactivate_already_inactive_account_returns_400(client, db):
    """POST /deactivate on an already-inactive account returns 400."""
    account = _make_account(db, is_active=False)
    response = client.post(
        f"/api/accounts/{account.id}/deactivate",
        json={"create_closing_snapshot": False},
    )
    assert response.status_code == 400
    assert "already inactive" in response.json()["detail"].lower()


def test_deactivate_nonexistent_account_returns_404(client):
    """POST /deactivate on a missing account returns 404."""
    response = client.post(
        "/api/accounts/does-not-exist/deactivate",
        json={"create_closing_snapshot": False},
    )
    assert response.status_code == 404


def test_deactivate_with_invalid_superseded_by_returns_400(client, account):
    """POST /deactivate with a non-existent replacement account returns 400."""
    response = client.post(
        f"/api/accounts/{account.id}/deactivate",
        json={
            "create_closing_snapshot": False,
            "superseded_by_account_id": "not-a-real-id",
        },
    )
    assert response.status_code == 400
    assert "replacement account not found" in response.json()["detail"].lower()


def test_deactivate_with_inactive_superseded_by_returns_400(client, db):
    """POST /deactivate with an inactive replacement account returns 400."""
    old = _make_account(db, provider="SimpleFIN", external_id="sf_1")
    inactive = _make_account(db, provider="Plaid", external_id="plaid_1", is_active=False)

    response = client.post(
        f"/api/accounts/{old.id}/deactivate",
        json={
            "create_closing_snapshot": False,
            "superseded_by_account_id": inactive.id,
        },
    )
    assert response.status_code == 400
    assert "replacement account must be active" in response.json()["detail"].lower()


def test_deactivate_self_supersede_returns_400(client, account):
    """POST /deactivate with superseded_by pointing to itself returns 400."""
    response = client.post(
        f"/api/accounts/{account.id}/deactivate",
        json={
            "create_closing_snapshot": False,
            "superseded_by_account_id": account.id,
        },
    )
    assert response.status_code == 400
    assert "cannot supersede itself" in response.json()["detail"].lower()


def test_deactivate_response_includes_superseded_by_name(client, db):
    """Response includes superseded_by_name populated from relationship."""
    old = _make_account(db, provider="SimpleFIN", external_id="sf_1")
    new = _make_account(db, provider="Plaid", external_id="plaid_1")

    response = client.post(
        f"/api/accounts/{old.id}/deactivate",
        json={
            "create_closing_snapshot": False,
            "superseded_by_account_id": new.id,
        },
    )
    data = response.json()
    assert data["superseded_by_name"] == "Plaid Test Account"
