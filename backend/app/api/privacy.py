"""Privacy, Data Protection, and Security API for DUIT.

Implements GDPR data export, right-to-be-forgotten data purging,
automated data retention enforcement, and SSRF URL verification.
"""
import hmac
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Header, Depends
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.db.repository import repository
from backend.app.security.auth_deps import get_current_user, AuthenticatedUser
from backend.app.security.ssrf import validate_safe_url


router = APIRouter(prefix="/api", tags=["Privacy and Security"])


class DataPurgePayload(BaseModel):
    confirm: bool = Field(..., description="Explicit confirmation required to initiate data purge")
    purge_messages: bool = Field(default=True, description="Purge archived WhatsApp message history")
    purge_approvals: bool = Field(default=True, description="Purge approval records")
    purge_executions: bool = Field(default=True, description="Purge execution logs")
    revoke_tokens: bool = Field(default=True, description="Revoke OAuth tokens and device credentials")


class RetentionCleanupPayload(BaseModel):
    tenant_id: str = "tenant_default_duit"
    retention_days: int = Field(..., ge=1, description="Data retention window in days")
    purge_messages: bool = True
    purge_executions: bool = True


class ValidateUrlPayload(BaseModel):
    url: str
    allowed_domains: Optional[List[str]] = None
    require_https: bool = False


def _verify_admin_or_gateway(secret: Optional[str]) -> None:
    """Verifies that the request carries valid administrator or gateway credentials."""
    if not settings.is_production and not secret:
        return
    expected = settings.GATEWAY_SHARED_SECRET
    if not expected:
        raise HTTPException(status_code=401, detail="Gateway secret not configured")
    if not secret or not hmac.compare_digest(secret.strip(), expected.strip()):
        raise HTTPException(status_code=401, detail="Unauthorized: invalid administrator/gateway secret")


@router.get("/privacy/export", response_model=Dict[str, Any])
async def export_user_data(
    user_id: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query("tenant_default_duit"),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Exports all personal data belonging to the user across accounts, messages, devices, and executions."""
    if user_id and not current_user.is_admin and user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Cannot export another user's data")
    resolved_user = current_user.user_id
    resolved_tenant = tenant_id or "tenant_default_duit"

    export_payload = await repository.export_user_data(
        tenant_id=resolved_tenant,
        user_id=resolved_user
    )
    return export_payload


@router.post("/privacy/purge", response_model=Dict[str, Any])
async def purge_user_data(
    payload: DataPurgePayload,
    user_id: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query("tenant_default_duit"),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Permanently purges or redacts data belonging to the user with mandatory explicit confirmation."""
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Data purge request rejected: 'confirm' must be explicitly set to True."
        )

    if user_id and not current_user.is_admin and user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Cannot purge another user's data")
    resolved_user = current_user.user_id
    resolved_tenant = tenant_id or "tenant_default_duit"

    result = await repository.purge_user_data(
        tenant_id=resolved_tenant,
        user_id=resolved_user,
        options=payload.model_dump()
    )
    return result


@router.post("/privacy/retention/cleanup", response_model=Dict[str, Any])
async def execute_retention_cleanup(
    payload: RetentionCleanupPayload,
    x_gateway_secret: Optional[str] = Header(None, alias="x-gateway-secret")
):
    """Executes data retention policy, purging data older than the configured threshold."""
    _verify_admin_or_gateway(x_gateway_secret)

    result = await repository.cleanup_retention(
        tenant_id=payload.tenant_id,
        retention_days=payload.retention_days,
        purge_messages=payload.purge_messages,
        purge_executions=payload.purge_executions
    )
    return result


@router.post("/security/validate-url", response_model=Dict[str, Any])
async def validate_outbound_url(payload: ValidateUrlPayload):
    """Verifies that an outbound URL does not target loopback, private, carrier-grade NAT, or cloud metadata networks."""
    is_safe, error_msg = validate_safe_url(
        url=payload.url,
        allowed_domains=payload.allowed_domains,
        require_https=payload.require_https
    )
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Unsafe URL: {error_msg}")

    return {
        "status": "valid",
        "url": payload.url,
        "is_safe": True
    }


@router.get("/security/audit/verify", response_model=Dict[str, Any])
async def verify_audit_log_integrity(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """Verifies immutability and record integrity of the audit log chain."""
    return await repository.verify_audit_log_integrity(tenant_id=tenant_id, limit=limit)
