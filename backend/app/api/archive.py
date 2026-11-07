"""FastAPI router for tenant-isolated WhatsApp message archive search & summary."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.app.db.repository import repository
from backend.app.security.context import SecurityContextError
from backend.app.security.auth_deps import get_current_user, AuthenticatedUser

router = APIRouter(prefix="/api/archive", tags=["WhatsApp Message Archive"])


class ArchiveSearchRequest(BaseModel):
    tenant_id: str = Field(..., description="Organizational tenant UUID")
    whatsapp_account_id: str = Field(..., description="Target linked WhatsApp account UUID")
    query: Optional[str] = Field(None, description="Keyword search string")
    contact: Optional[str] = Field(None, description="Contact name or phone number filter")
    sender_phone: Optional[str] = Field(None, description="Sender phone number filter")
    direction: Optional[str] = Field(None, description="inbound or outbound")
    start_date: Optional[datetime] = Field(None, description="Start timestamp filter")
    end_date: Optional[datetime] = Field(None, description="End timestamp filter")
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class ArchiveSummaryRequest(BaseModel):
    tenant_id: str = Field(..., description="Organizational tenant UUID")
    whatsapp_account_id: str = Field(..., description="Target linked WhatsApp account UUID")
    query: Optional[str] = Field(None, description="Topic or query to filter summary")
    contact: Optional[str] = Field(None, description="Contact name or phone number")
    limit: int = Field(10, ge=1, le=50, description="Maximum messages to summarize")


@router.post("/search")
async def search_archive(
    req: ArchiveSearchRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Searches archived WhatsApp messages strictly isolated to tenant and linked WhatsApp account."""
    # Verify account belongs to tenant
    account = await repository.get_whatsapp_account(req.whatsapp_account_id, tenant_id=req.tenant_id)
    if not account:
        raise HTTPException(
            status_code=400,
            detail=f"WhatsApp account {req.whatsapp_account_id} not found in tenant {req.tenant_id}"
        )
    if not current_user.is_admin and account.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's WhatsApp archive")

    results = await repository.search_messages(
        tenant_id=req.tenant_id,
        whatsapp_account_id=req.whatsapp_account_id,
        query_text=req.query,
        contact=req.contact,
        sender_phone=req.sender_phone,
        direction=req.direction,
        start_date=req.start_date,
        end_date=req.end_date,
        limit=req.limit,
        offset=req.offset
    )

    return {
        "status": "success",
        "tenant_id": req.tenant_id,
        "whatsapp_account_id": req.whatsapp_account_id,
        "count": len(results),
        "limit": req.limit,
        "offset": req.offset,
        "messages": results
    }


@router.post("/summary")
async def summarize_archive(
    req: ArchiveSummaryRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Generates structured summary of archived messages with source citations and truthful absence reporting."""
    account = await repository.get_whatsapp_account(req.whatsapp_account_id, tenant_id=req.tenant_id)
    if not account:
        raise HTTPException(
            status_code=400,
            detail=f"WhatsApp account {req.whatsapp_account_id} not found in tenant {req.tenant_id}"
        )
    if not current_user.is_admin and account.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's WhatsApp archive")

    summary = await repository.generate_archive_summary(
        tenant_id=req.tenant_id,
        whatsapp_account_id=req.whatsapp_account_id,
        query_text=req.query,
        contact=req.contact,
        limit=req.limit
    )

    return {
        "status": "success",
        "tenant_id": req.tenant_id,
        "whatsapp_account_id": req.whatsapp_account_id,
        "total_found": summary["total_found"],
        "citations": summary["citations"],
        "summary_text": summary["summary_text"],
        "messages": summary["messages"]
    }
