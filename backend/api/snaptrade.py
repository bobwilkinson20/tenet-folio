"""SnapTrade connection management API endpoints.

Provides endpoints to list, add, remove, and refresh brokerage
connections via the SnapTrade SDK.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/snaptrade", tags=["snaptrade"])


def _get_attr(obj: object, key: str, default: object = None) -> object:
    """Get attribute from dict or object (SDK responses vary)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class _SnapTradeSDK:
    """Lightweight wrapper providing the SnapTrade SDK client and user creds."""

    def __init__(self) -> None:
        from services.credential_manager import get_credential

        client_id = get_credential("SNAPTRADE_CLIENT_ID")
        consumer_key = get_credential("SNAPTRADE_CONSUMER_KEY")
        if not client_id or not consumer_key:
            raise HTTPException(
                status_code=400,
                detail="SnapTrade is not configured. Set up credentials first.",
            )

        self.user_id = get_credential("SNAPTRADE_USER_ID") or ""
        self.user_secret = get_credential("SNAPTRADE_USER_SECRET") or ""
        if not self.user_id or not self.user_secret:
            raise HTTPException(
                status_code=400,
                detail="SnapTrade user not registered. Run setup first.",
            )

        from snaptrade_client import SnapTrade

        self.client = SnapTrade(consumer_key=consumer_key, client_id=client_id)


def _get_sdk() -> _SnapTradeSDK:
    """Dependency for injecting the SnapTrade SDK (overridable in tests)."""
    return _SnapTradeSDK()


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------


class SnapTradeConnectionResponse(BaseModel):
    authorization_id: str
    brokerage_name: str
    name: str
    disabled: bool
    disabled_date: str | None = None
    error_message: str | None = None


class ConnectUrlResponse(BaseModel):
    redirect_url: str


class RemoveConnectionResponse(BaseModel):
    status: str
    authorization_id: str


class ReconnectUrlResponse(BaseModel):
    redirect_url: str
    authorization_id: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/connections", response_model=list[SnapTradeConnectionResponse])
def list_connections(sdk: _SnapTradeSDK = Depends(_get_sdk)):
    """List all SnapTrade brokerage connections."""
    try:
        response = sdk.client.connections.list_brokerage_authorizations(
            user_id=sdk.user_id,
            user_secret=sdk.user_secret,
        )
        authorizations = response if isinstance(response, list) else response.body
    except Exception as e:
        logger.error("Failed to list SnapTrade connections: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list connections")

    result = []
    for auth in authorizations:
        auth_id = str(_get_attr(auth, "id", ""))

        # Brokerage name may be nested under a brokerage object
        brokerage_obj = _get_attr(auth, "brokerage")
        if brokerage_obj:
            brokerage_name = str(_get_attr(brokerage_obj, "name", "Unknown"))
        else:
            brokerage_name = "Unknown"

        conn_name = str(_get_attr(auth, "name", brokerage_name))
        disabled = bool(_get_attr(auth, "disabled", False))
        disabled_date = _get_attr(auth, "disabled_date")
        disabled_date_str = str(disabled_date) if disabled_date else None

        # SnapTrade doesn't have a single error_message field, but disabled
        # connections may have a meta object with details
        meta = _get_attr(auth, "meta")
        error_message = None
        if meta:
            error_message = str(_get_attr(meta, "status_message", "")) or None

        result.append(
            SnapTradeConnectionResponse(
                authorization_id=auth_id,
                brokerage_name=brokerage_name,
                name=conn_name,
                disabled=disabled,
                disabled_date=disabled_date_str,
                error_message=error_message,
            )
        )

    return result


@router.post("/connect-url", response_model=ConnectUrlResponse)
def create_connect_url(sdk: _SnapTradeSDK = Depends(_get_sdk)):
    """Generate a redirect URL for brokerage OAuth connection."""
    try:
        response = sdk.client.authentication.login_snap_trade_user(
            user_id=sdk.user_id,
            user_secret=sdk.user_secret,
        )
        body = response.body if hasattr(response, "body") else response
        redirect_url = (
            _get_attr(body, "redirectURI")
            or _get_attr(body, "redirect_uri")
            or _get_attr(body, "loginRedirectURI")
        )
        if not redirect_url:
            logger.error("Unexpected SnapTrade login response: %s", body)
            raise HTTPException(
                status_code=500, detail="Failed to generate connect URL"
            )
        return ConnectUrlResponse(redirect_url=str(redirect_url))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate SnapTrade connect URL: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate connect URL")


@router.delete(
    "/connections/{authorization_id}",
    response_model=RemoveConnectionResponse,
)
def remove_connection(
    authorization_id: str,
    sdk: _SnapTradeSDK = Depends(_get_sdk),
):
    """Remove a SnapTrade brokerage connection."""
    try:
        sdk.client.connections.remove_brokerage_authorization(
            authorization_id=authorization_id,
            user_id=sdk.user_id,
            user_secret=sdk.user_secret,
        )
        logger.info("Removed SnapTrade connection %s", authorization_id)
        return RemoveConnectionResponse(
            status="ok", authorization_id=authorization_id
        )
    except Exception as e:
        logger.error(
            "Failed to remove SnapTrade connection %s: %s", authorization_id, e
        )
        raise HTTPException(status_code=500, detail="Failed to remove connection")


@router.post(
    "/connections/{authorization_id}/refresh",
    response_model=ReconnectUrlResponse,
)
def refresh_connection(
    authorization_id: str,
    sdk: _SnapTradeSDK = Depends(_get_sdk),
):
    """Generate a reconnect URL for re-authenticating a brokerage connection."""
    try:
        response = sdk.client.authentication.login_snap_trade_user(
            user_id=sdk.user_id,
            user_secret=sdk.user_secret,
            reconnect=authorization_id,
        )
        body = response.body if hasattr(response, "body") else response
        redirect_url = (
            _get_attr(body, "redirectURI")
            or _get_attr(body, "redirect_uri")
            or _get_attr(body, "loginRedirectURI")
        )
        if not redirect_url:
            logger.error("Unexpected SnapTrade reconnect response: %s", body)
            raise HTTPException(
                status_code=500, detail="Failed to generate reconnect URL"
            )
        logger.info("Generated reconnect URL for connection %s", authorization_id)
        return ReconnectUrlResponse(
            redirect_url=str(redirect_url),
            authorization_id=authorization_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to generate reconnect URL for connection %s: %s",
            authorization_id,
            e,
        )
        raise HTTPException(
            status_code=500, detail="Failed to generate reconnect URL"
        )
