"""FastAPI router for secure, multi-tenant WhatsApp linking transactions."""
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from backend.app.db.repository import repository
from backend.app.security.context import SecurityContextError
from backend.app.security.auth_deps import get_current_user, AuthenticatedUser
from backend.app.config import settings


router = APIRouter(prefix="/api/linking", tags=["WhatsApp Linking"])


class CreateLinkingSessionRequest(BaseModel):
    tenant_id: str = Field(..., description="Organizational tenant UUID")
    user_id: str = Field(..., description="Target user UUID")
    phone_number: Optional[str] = Field(None, description="Optional intended WhatsApp phone number")
    gateway_instance: str = Field("directorbot-primary", description="Target gateway instance identifier")
    ttl_seconds: int = Field(600, description="Session TTL in seconds (default 10 minutes)")


class ConfirmPairingRequest(BaseModel):
    nonce: str = Field(..., description="One-time nonce bound to the linking transaction")
    pairing_code: str = Field(..., description="One-time pairing code")
    phone_number: Optional[str] = Field(None, description="Verified WhatsApp phone number")
    encrypted_credentials: Optional[str] = Field(None, description="AES-256-GCM encrypted Baileys session credentials")
    key_version: int = Field(1, description="Encryption key version")


class RevokeSessionRequest(BaseModel):
    caller_user_id: Optional[str] = Field(None, description="User requesting revocation")


@router.post("/sessions", status_code=201)
async def create_linking_session(
    req: CreateLinkingSessionRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Initializes a short-lived, dedicated transaction for linking a WhatsApp account."""
    try:
        if not current_user.is_admin and current_user.user_id != req.user_id:
            raise HTTPException(status_code=403, detail="Cannot link an account for another user")
        session = await repository.create_linking_session(
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            phone_number=req.phone_number,
            gateway_instance=req.gateway_instance,
            ttl_seconds=req.ttl_seconds
        )
        return {
            "session_id": session["id"],
            "pairing_code": session["pairing_code"],
            "nonce": session["nonce"],
            "status": session["status"],
            "expires_at": session["expires_at"],
            "gateway_instance": session["gateway_instance"]
        }
    except SecurityContextError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create linking session: {str(e)}")


@router.get("/sessions/{session_id}/status")
async def get_linking_session_status(
    session_id: str,
    x_tenant_id: Optional[str] = Header(None),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Retrieves the current status of a WhatsApp linking transaction."""
    session = await repository.get_linking_session(session_id, tenant_id=x_tenant_id)
    if not session:
        raise HTTPException(status_code=404, detail="Linking session not found")
    if not current_user.is_admin and session["user_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Cannot inspect another user's linking session")
    return {
        "session_id": session["id"],
        "status": session["status"],
        "tenant_id": session["tenant_id"],
        "user_id": session["user_id"],
        "whatsapp_account_id": session.get("whatsapp_account_id"),
        "phone_number": session.get("phone_number"),
        "expires_at": session["expires_at"]
    }


@router.post("/sessions/{session_id}/pair")
async def confirm_session_pairing(
    session_id: str,
    req: ConfirmPairingRequest,
    x_gateway_secret: Optional[str] = Header(None, alias="x-gateway-secret")
):
    """Confirms WhatsApp account pairing using one-time pairing code and nonce."""
    if settings.is_production:
        expected = settings.GATEWAY_SHARED_SECRET
        if not expected or not x_gateway_secret:
            raise HTTPException(status_code=401, detail="Gateway authentication required")
        import hmac
        if not hmac.compare_digest(x_gateway_secret.strip(), expected.strip()):
            raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        result = await repository.confirm_pairing(
            session_id=session_id,
            nonce=req.nonce,
            pairing_code=req.pairing_code,
            encrypted_credentials=req.encrypted_credentials,
            phone_number=req.phone_number,
            key_version=req.key_version
        )
        return result
    except SecurityContextError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pairing confirmation failed: {str(e)}")


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: str,
    req: Optional[RevokeSessionRequest] = None,
    x_user_id: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None)
):
    """Revokes a WhatsApp linking session and invalidates associated credentials."""
    caller_id = (req.caller_user_id if req and req.caller_user_id else None) or x_user_id
    if not caller_id:
        raise HTTPException(status_code=401, detail="Caller user identification required (x-user-id header or body).")

    try:
        result = await repository.revoke_linking_session(
            session_id=session_id,
            caller_user_id=caller_id,
            tenant_id=x_tenant_id
        )
        return result
    except SecurityContextError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Revocation failed: {str(e)}")
