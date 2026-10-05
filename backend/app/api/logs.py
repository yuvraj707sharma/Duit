"""Audit Logs & Action History API."""
from typing import Optional
from fastapi import APIRouter, Query
from backend.app.cascade.orchestrator import cascade_orchestrator

router = APIRouter(prefix="/api/audit-logs", tags=["Audit Logs"])


@router.get("")
async def list_audit_logs(
    user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50)
):
    return await cascade_orchestrator.repo.get_audit_logs(user_id=user_id, limit=limit)
