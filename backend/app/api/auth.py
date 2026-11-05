"""Google OAuth 2.0 Auth API with AES-GCM Encrypted Token Storage."""
import hmac
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request, Header
from fastapi.responses import RedirectResponse
from backend.app.security.oauth import generate_auth_url, get_oauth_flow
from backend.app.security.crypto import encrypt_token
from backend.app.db.repository import repository
from backend.app.config import settings
from backend.app.channels.evolution import EvolutionChannel
from backend.app.channels.mock import MockChannel

router = APIRouter(prefix="/api/auth", tags=["Auth"])

outbound_channel = EvolutionChannel() if settings.MESSAGING_CHANNEL == "evolution" else MockChannel()


@router.get("/google/url")
async def get_google_auth_url(
    user_id: str = Query(default="default_user"),
    redirect: bool = Query(default=False)
):
    try:
        url = generate_auth_url(user_id=user_id)
    except Exception:
        url = f"https://accounts.google.com/o/oauth2/auth?mock_for_user={user_id}"

    if redirect:
        return RedirectResponse(url=url)
    return {"auth_url": url}


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(default="default_user")
):
    try:
        flow = get_oauth_flow(state=state)
        flow.fetch_token(code=code)
        credentials = flow.credentials

        encrypted_access = encrypt_token(credentials.token, user_id=state)
        encrypted_refresh = encrypt_token(credentials.refresh_token or "", user_id=state)
    except Exception as exc:
        if not settings.is_production:
            # Safe mock fallback for local testing and dev
            encrypted_access = encrypt_token(f"mock_access_token_for_{state}", user_id=state)
            encrypted_refresh = encrypt_token(f"mock_refresh_token_for_{state}", user_id=state)
        else:
            raise HTTPException(status_code=502, detail="OAuth token exchange failed") from exc

    # Persist encrypted tokens securely in repository
    await repository.save_user_oauth_tokens(
        user_id=state,
        provider="google",
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh
    )

    # Check if user is known by state (UUID or phone) and send WhatsApp notification
    user = await repository.get_user(state)
    if not user and state.replace("+", "").isdigit():
        user = await repository.register_user(phone=state)

    user_phone = user.get("phone_number") if user else (state if state.replace("+", "").isdigit() else None)
    if user_phone:
        welcome_msg = (
            "*Google Account Successfully Linked!*\n\n"
            "DUIT is now active for your calendar and email.\n\n"
            "Try asking me:\n"
            "- *\"What meetings do I have tomorrow?\"*\n"
            "- *\"Check unread emails from Priya\"*\n"
            "- *\"Schedule sync with Team on Friday at 4pm\"*"
        )
        try:
            await outbound_channel.send_text(user_phone, welcome_msg)
        except Exception:
            pass

    # If accessed through browser, redirect to success landing screen
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header or request.query_params.get("redirect") == "true":
        return RedirectResponse(url=f"/connect/success?user_id={state}")

    return {
        "status": "success",
        "user_id": state,
        "message": "Google Account linked successfully. Tokens encrypted with AES-256-GCM."
    }


from pydantic import BaseModel


class SaveTokenRequest(BaseModel):
    user_id: str
    access_token: str
    refresh_token: Optional[str] = None
    expiry_date: Optional[int] = None
    email: Optional[str] = None
    provider: Optional[str] = "google"


def _verify_gateway_secret(provided: Optional[str]) -> None:
    """Verify gateway shared secret with constant-time comparison."""
    if not settings.is_production and not provided:
        return
    expected = settings.GATEWAY_SHARED_SECRET
    if not expected:
        raise HTTPException(status_code=401, detail="Gateway secret not configured")
    if not provided or not hmac.compare_digest(provided.strip(), expected.strip()):
        raise HTTPException(status_code=401, detail="Unauthorized: invalid gateway secret")


@router.post("/save-token")
async def save_oauth_token(
    req: SaveTokenRequest,
    x_gateway_secret: Optional[str] = Header(None, alias="x-gateway-secret")
):
    """Direct ingestion endpoint for OAuth tokens obtained via gateway. Requires server-to-server auth."""
    _verify_gateway_secret(x_gateway_secret)

    user_id = req.user_id.strip().lstrip("+")
    encrypted_access = encrypt_token(req.access_token, user_id=user_id)
    encrypted_refresh = encrypt_token(req.refresh_token or "", user_id=user_id) if req.refresh_token else None

    await repository.save_user_oauth_tokens(
        user_id=user_id,
        provider=req.provider or "google",
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh
    )

    # Store encrypted reference in memory for fast access by Google Calendar & Gmail tools
    if user_id in repository.tokens_store:
        repository.tokens_store[user_id]["encrypted_access_token"] = encrypted_access
        repository.tokens_store[user_id]["encrypted_refresh_token"] = encrypted_refresh
        repository.tokens_store[user_id]["email"] = req.email

    return {"status": "success", "user_id": user_id, "email": req.email}
