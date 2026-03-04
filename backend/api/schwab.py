"""Schwab OAuth API endpoints.

Provides the server-side endpoints for the Schwab OAuth authorization
flow: generating auth URLs, exchanging authorization codes for tokens,
checking token status, and an optional auto-intercept callback.
"""

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schwab", tags=["schwab"])

# ------------------------------------------------------------------
# In-memory auth context storage (state → (context, created_at))
# ------------------------------------------------------------------

_auth_contexts: dict[str, tuple[object, float]] = {}
AUTH_CONTEXT_TTL = 600  # 10 minutes


def _cleanup_expired_contexts() -> None:
    """Remove auth contexts older than TTL."""
    now = time.time()
    expired = [s for s, (_, ts) in _auth_contexts.items() if now - ts > AUTH_CONTEXT_TTL]
    for s in expired:
        del _auth_contexts[s]


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class AuthUrlResponse(BaseModel):
    authorization_url: str
    state: str


class TokenExchangeRequest(BaseModel):
    state: str
    received_url: str


class TokenExchangeResponse(BaseModel):
    message: str
    account_count: int


class TokenStatusResponse(BaseModel):
    status: str  # "valid", "expiring_soon", "expired", "no_token", "no_credentials"
    message: str
    expires_at: str | None = None
    days_remaining: float | None = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/auth-url", response_model=AuthUrlResponse)
def create_auth_url():
    """Generate a Schwab OAuth authorization URL."""
    if not settings.SCHWAB_APP_KEY or not settings.SCHWAB_CALLBACK_URL:
        raise HTTPException(
            status_code=400,
            detail="Schwab is not configured. Set up App Key and Callback URL first.",
        )

    try:
        from schwab.auth import get_auth_context
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="schwab-py library is not installed.",
        )

    _cleanup_expired_contexts()

    try:
        auth_context = get_auth_context(
            settings.SCHWAB_APP_KEY, settings.SCHWAB_CALLBACK_URL
        )
    except Exception as e:
        logger.error("Failed to create Schwab auth context: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate authorization URL: {e}",
        )

    _auth_contexts[auth_context.state] = (auth_context, time.time())
    logger.info("Generated Schwab auth URL (state=%s...)", auth_context.state[:8])

    return AuthUrlResponse(
        authorization_url=auth_context.authorization_url,
        state=auth_context.state,
    )


@router.post("/exchange-token", response_model=TokenExchangeResponse)
def exchange_token(body: TokenExchangeRequest):
    """Exchange an OAuth authorization code for a token."""
    _cleanup_expired_contexts()

    context_entry = _auth_contexts.get(body.state)
    if context_entry is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired authorization state. Please start the OAuth flow again.",
        )

    auth_context, created_at = context_entry
    if time.time() - created_at > AUTH_CONTEXT_TTL:
        del _auth_contexts[body.state]
        raise HTTPException(
            status_code=400,
            detail="Authorization session expired. Please start the OAuth flow again.",
        )

    try:
        from schwab.auth import client_from_received_url
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="schwab-py library is not installed.",
        )

    token_path = settings.SCHWAB_TOKEN_PATH
    if not token_path:
        token_path = str(Path(__file__).parent.parent / ".schwab_token.json")

    def token_write_func(token_data, _=None):
        """Write token JSON to disk with restrictive permissions."""
        p = Path(token_path)
        p.write_text(json.dumps(token_data, indent=2))
        p.chmod(0o600)
        logger.info("Schwab token written to %s", token_path)

    try:
        client = client_from_received_url(
            api_key=settings.SCHWAB_APP_KEY,
            app_secret=settings.SCHWAB_APP_SECRET,
            auth_context=auth_context,
            received_url=body.received_url,
            token_write_func=token_write_func,
        )
    except Exception as e:
        logger.error("Schwab token exchange failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail=f"Token exchange failed: {e}",
        )

    # Validate by fetching account numbers
    account_count = 0
    try:
        resp = client.get_account_numbers()
        if resp.status_code == 200:
            account_count = len(resp.json())
    except Exception as e:
        logger.warning("Could not validate Schwab token (continuing): %s", e)

    # Clean up used context
    _auth_contexts.pop(body.state, None)

    logger.info(
        "Schwab OAuth complete — %d account(s) found", account_count
    )
    return TokenExchangeResponse(
        message=f"Schwab authorized successfully. Found {account_count} account(s).",
        account_count=account_count,
    )


@router.get("/token-status", response_model=TokenStatusResponse)
def get_token_status():
    """Check the status of the Schwab OAuth token."""
    if not settings.SCHWAB_APP_KEY or not settings.SCHWAB_APP_SECRET:
        return TokenStatusResponse(
            status="no_credentials",
            message="Schwab is not configured.",
        )

    token_path = settings.SCHWAB_TOKEN_PATH
    if not token_path:
        token_path = str(Path(__file__).parent.parent / ".schwab_token.json")

    p = Path(token_path)
    if not p.exists():
        return TokenStatusResponse(
            status="no_token",
            message="No OAuth token found. Complete the authorization flow to connect.",
        )

    try:
        token_data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read Schwab token file: %s", e)
        return TokenStatusResponse(
            status="no_token",
            message="Token file is corrupted or unreadable.",
        )

    creation_ts = token_data.get("creation_timestamp")
    if creation_ts is None:
        return TokenStatusResponse(
            status="no_token",
            message="Token file is missing creation timestamp.",
        )

    age_seconds = time.time() - creation_ts
    age_days = age_seconds / 86400.0

    if age_days > 6.5:
        return TokenStatusResponse(
            status="expired",
            message="Schwab token has expired. Re-authorize to continue syncing.",
            days_remaining=max(0, 7.0 - age_days),
        )
    elif age_days > 5:
        days_left = 7.0 - age_days
        return TokenStatusResponse(
            status="expiring_soon",
            message=f"Schwab token expires in {days_left:.1f} days. Re-authorize soon.",
            days_remaining=days_left,
        )
    else:
        days_left = 7.0 - age_days
        return TokenStatusResponse(
            status="valid",
            message=f"Schwab token is valid ({days_left:.1f} days remaining).",
            days_remaining=days_left,
        )


def _callback_html(title: str, message: str, *, success: bool) -> HTMLResponse:
    """Return a small HTML page that auto-closes the tab.

    The Schwab OAuth callback opens in a tab created by ``window.open``.
    Browsers allow ``window.close()`` for script-opened tabs, so this
    page closes itself after a brief delay.  A fallback message is shown
    in case the browser blocks the close.
    """
    color = "#16a34a" if success else "#dc2626"
    icon = "&#10003;" if success else "&#10007;"
    html = f"""\
<!DOCTYPE html>
<html><head><title>{title}</title></head>
<body style="display:flex;align-items:center;justify-content:center;height:100vh;
  margin:0;font-family:system-ui,sans-serif;background:#f9fafb;color:#111">
<div style="text-align:center">
  <div style="font-size:3rem;color:{color}">{icon}</div>
  <h2>{title}</h2>
  <p>{message}</p>
  <p style="color:#6b7280;font-size:.875rem" id="hint">Closing this tab&hellip;</p>
</div>
<script>
  setTimeout(function(){{
    window.close();
    document.getElementById("hint").textContent="You can close this tab.";
  }},1500);
</script>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/callback")
def oauth_callback(
    code: str = Query(default=""),
    session: str = Query(default=""),
    state: str = Query(default=""),
):
    """Auto-intercept OAuth callback from Schwab.

    Schwab redirects with three query params: ``code`` (authorization
    code), ``session`` (Schwab's internal session), and ``state`` (the
    OAuth state we originally sent).  This endpoint looks up the pending
    auth context by ``state``, reconstructs the received URL, exchanges
    the token, and returns a self-closing HTML page.  The original
    settings tab detects the new token via polling.
    """
    if not code:
        return _callback_html(
            "Authorization Failed",
            "Missing authorization code.",
            success=False,
        )

    _cleanup_expired_contexts()

    # Look up by state (our OAuth CSRF token, echoed back by Schwab)
    context_entry = _auth_contexts.get(state) if state else None
    if context_entry is None:
        logger.error(
            "Schwab callback: no matching context for state=%s... "
            "(pending_contexts=%d)",
            state[:8] if state else "(empty)",
            len(_auth_contexts),
        )
        return _callback_html(
            "Authorization Failed",
            "Invalid or expired authorization. Please try again from Settings.",
            success=False,
        )

    auth_context, _created_at = context_entry

    # Reconstruct the full received URL for schwab-py
    received_url = (
        f"{settings.SCHWAB_CALLBACK_URL}"
        f"?code={code}&session={session}&state={state}"
    )

    try:
        from schwab.auth import client_from_received_url
    except ImportError:
        return _callback_html(
            "Authorization Failed",
            "schwab-py library is not installed.",
            success=False,
        )

    token_path = settings.SCHWAB_TOKEN_PATH
    if not token_path:
        token_path = str(Path(__file__).parent.parent / ".schwab_token.json")

    def token_write_func(token_data, _=None):
        p = Path(token_path)
        p.write_text(json.dumps(token_data, indent=2))
        p.chmod(0o600)

    try:
        client_from_received_url(
            api_key=settings.SCHWAB_APP_KEY,
            app_secret=settings.SCHWAB_APP_SECRET,
            auth_context=auth_context,
            received_url=received_url,
            token_write_func=token_write_func,
        )
    except Exception as e:
        logger.error("Schwab callback token exchange failed: %s", e)
        return _callback_html(
            "Authorization Failed",
            f"Token exchange failed: {e}",
            success=False,
        )

    _auth_contexts.pop(state, None)
    logger.info("Schwab OAuth callback successful")

    return _callback_html(
        "Schwab Authorized",
        "Token saved successfully. This tab will close automatically.",
        success=True,
    )
