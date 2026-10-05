"""Approvals and Human-in-the-Loop Management API."""
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel
from backend.app.cascade.orchestrator import cascade_orchestrator

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


class ResolveApprovalRequest(BaseModel):
    decision: str  # approve, edit, reject
    user_id: Optional[str] = None
    edited_payload: Optional[Dict[str, Any]] = None
    user_feedback: Optional[str] = None


@router.get("")
async def list_pending_approvals(user_id: Optional[str] = Query(default=None)):
    if user_id:
        approvals = await cascade_orchestrator.get_pending_approvals(user_id)
    else:
        approvals = list(cascade_orchestrator.repo.approvals_store.values())
    return sorted(approvals, key=lambda x: x.get("created_at", 0), reverse=True)


@router.post("/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    req: ResolveApprovalRequest,
    user_id: Optional[str] = Query(default=None)
):
    caller_id = req.user_id or user_id or "default_user"
    if req.decision not in ("approve", "edit", "reject"):
        raise HTTPException(status_code=400, detail="Invalid decision; must be 'approve', 'edit', or 'reject'")

    res = await cascade_orchestrator.resolve_approval(
        approval_id=approval_id,
        decision=req.decision,
        caller_user_id=caller_id,
        edited_payload=req.edited_payload
    )

    if "error" in res:
        err_msg = res["error"]
        if "Unauthorized" in err_msg:
            raise HTTPException(status_code=403, detail=err_msg)
        elif "expired" in err_msg.lower():
            raise HTTPException(status_code=410, detail=err_msg)
        raise HTTPException(status_code=404, detail=err_msg)
    return res
