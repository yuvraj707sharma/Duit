"""Approvals and Human-in-the-Loop Management API with Centralized Auth & Ownership Checks."""
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from backend.app.cascade.orchestrator import cascade_orchestrator
from backend.app.security.auth_deps import get_current_user, get_optional_current_user, AuthenticatedUser, require_user_access
from backend.app.config import settings

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


class ResolveApprovalRequest(BaseModel):
    decision: str  # approve, edit, reject
    edited_payload: Optional[Dict[str, Any]] = None
    user_feedback: Optional[str] = None


@router.get("")
async def list_pending_approvals(
    user_id: Optional[str] = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Lists pending approvals.
    Regular users may only view their own approvals; administrators may view broader data.
    """
    if user_id:
        require_user_access(user_id, current_user)
        target_user = user_id
    elif not current_user.is_admin:
        target_user = current_user.user_id
    else:
        target_user = None

    if target_user:
        approvals = await cascade_orchestrator.get_pending_approvals(target_user)
    else:
        approvals = list(cascade_orchestrator.repo.approvals_store.values())

    return sorted(approvals, key=lambda x: x.get("created_at", 0), reverse=True)


@router.post("/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    req: ResolveApprovalRequest,
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Resolves a pending approval.
    Enforces that caller is authenticated and matches the approval owner.
    """
    if req.decision not in ("approve", "edit", "reject"):
        raise HTTPException(status_code=400, detail="Invalid decision; must be 'approve', 'edit', or 'reject'")

    # Pre-verification: Verify approval ID belongs to authenticated user
    existing_approval = cascade_orchestrator.repo.approvals_store.get(approval_id)
    if existing_approval:
        approval_owner = existing_approval.get("user_id", "")
        if approval_owner and not current_user.is_admin:
            require_user_access(approval_owner, current_user)

    caller_id = current_user.user_id

    res = await cascade_orchestrator.resolve_approval(
        approval_id=approval_id,
        decision=req.decision,
        caller_user_id=caller_id,
        edited_payload=req.edited_payload
    )

    if "error" in res:
        err_msg = res["error"]
        if "Unauthorized" in err_msg or "mismatch" in err_msg.lower():
            raise HTTPException(status_code=403, detail=err_msg)
        elif "expired" in err_msg.lower():
            raise HTTPException(status_code=410, detail=err_msg)
        raise HTTPException(status_code=404, detail=err_msg)
    return res


class AmendApprovalRequest(BaseModel):
    amendments: Dict[str, Any]
    caller_user_id: Optional[str] = None


@router.post("/{approval_id}/amend")
async def amend_approval(
    approval_id: str,
    req: AmendApprovalRequest,
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_current_user)
):
    """Amends a pending approval's arguments in place."""
    if settings.is_production and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    caller_id = current_user.user_id if current_user else (req.caller_user_id or "default_user")
    res = await cascade_orchestrator.repo.amend_approval(
        approval_id=approval_id,
        caller_user_id=caller_id,
        amendments=req.amendments
    )
    if "error" in res:
        err = res["error"]
        if "Unauthorized" in err:
            raise HTTPException(status_code=403, detail=err)
        elif "expired" in err.lower():
            raise HTTPException(status_code=410, detail=err)
        raise HTTPException(status_code=400, detail=err)
    return res


@router.post("/cleanup")
async def cleanup_expired_approvals():
    """Transitions expired approvals to expired state."""
    count = await cascade_orchestrator.repo.cleanup_expired_approvals()
    return {"status": "success", "expired_cleaned": count}
