"""Audit Logs & Action History API with Centralized Auth & User Scoping."""
from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from backend.app.cascade.orchestrator import cascade_orchestrator
from backend.app.security.auth_deps import get_current_user, AuthenticatedUser, require_user_access

router = APIRouter(prefix="/api/audit-logs", tags=["Audit Logs"])


@router.get("")
async def list_audit_logs(
    user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Retrieves audit logs.
    Authenticated users can only view their own logs; administrators can view broader data.
    """
    if user_id:
        require_user_access(user_id, current_user)
        target_user = user_id
    elif not current_user.is_admin:
        target_user = current_user.user_id
    else:
        target_user = None

    return await cascade_orchestrator.repo.get_audit_logs(user_id=target_user, limit=limit)
