"""
Auth router — Yahoo OAuth 2.0 flow.

GET /auth/yahoo          → redirect user to Yahoo authorization page
GET /auth/yahoo/callback → exchange code for access + refresh tokens

After the callback, copy YAHOO_REFRESH_TOKEN from server logs to .env.
The app auto-refreshes the token on every subsequent API call.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from backend.config import settings
from backend.integrations.yahoo_api import (
    exchange_code_for_tokens,
    get_authorization_url,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/yahoo", summary="Redirect to Yahoo OAuth authorization page")
async def yahoo_login():
    """
    Initiate Yahoo OAuth flow.
    Opens Yahoo's authorization page where the user grants Fantasy Sports access.
    """
    if not settings.yahoo_client_id:
        raise HTTPException(
            status_code=500,
            detail="YAHOO_CLIENT_ID not configured — add it to .env and restart",
        )
    url = get_authorization_url()
    logger.info("Redirecting to Yahoo OAuth: %s", url[:60] + "...")
    return RedirectResponse(url=url)


@router.get("/yahoo/callback", summary="Yahoo OAuth callback — exchange code for tokens")
async def yahoo_callback(code: str):
    """
    Yahoo redirects here after the user authorizes the app.
    Exchanges the authorization code for access + refresh tokens.

    Copy the YAHOO_REFRESH_TOKEN printed in server logs to your .env file.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        tokens = await exchange_code_for_tokens(code)
    except Exception as exc:
        logger.error("Yahoo OAuth token exchange failed: %s", exc)
        raise HTTPException(
            status_code=400, detail=f"Token exchange failed: {exc}"
        ) from exc

    refresh_token = tokens.get("refresh_token", "")
    access_token = tokens.get("access_token", "")

    if refresh_token:
        # Log at INFO so the user can copy it — do not expose in HTTP response body
        logger.info(
            "Yahoo OAuth complete. Add to .env:\n  YAHOO_REFRESH_TOKEN=%s",
            refresh_token,
        )
    else:
        logger.warning("Yahoo did not return a refresh token — check app scope settings")

    return {
        "status": "ok",
        "message": (
            "OAuth complete. Copy YAHOO_REFRESH_TOKEN from server logs to .env, "
            "then restart the app."
        ),
        "has_access_token": bool(access_token),
        "has_refresh_token": bool(refresh_token),
        # Never return tokens in the response body
    }
