"""Repository layer managing database persistence for FastAgent."""
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import PendingApproval, AuditLog, IdempotencyRecord, LearningCorrection, utc_now


class DatabaseRepository:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory
        # In-memory fast layer backed by database schema
        self.approvals_store: Dict[str, Dict[str, Any]] = {}
        self.audit_log_store: List[Dict[str, Any]] = []
        self.idempotency_store: Dict[str, Dict[str, Any]] = {}
        self.webhook_dedupe_store: Dict[str, Dict[str, Any]] = {}

    async def create_pending_approval(
        self,
        user_id: str,
        request_id: str,
        query_text: str,
        intent: str,
        risk: str,
        confidence: float,
        arguments: Dict[str, Any],
        expires_in_seconds: int = 300
    ) -> Dict[str, Any]:
        now = time.time()
        expires_at = now + expires_in_seconds
        
        # Enforce Fix 2: Single pending approval per user (supersede prior pending)
        for aid, rec in self.approvals_store.items():
            if rec["user_id"] == user_id and rec["status"] == "pending":
                rec["status"] = "superseded"
                rec["resolved_at"] = now

        approval_id = str(uuid.uuid4())
        record = {
            "id": approval_id,
            "user_id": user_id,
            "request_id": request_id,
            "query_text": query_text,
            "intent": intent,
            "risk": risk,
            "confidence": confidence,
            "arguments": arguments,
            "status": "pending",
            "created_at": now,
            "expires_at": expires_at,
            "resolved_at": None
        }
        self.approvals_store[approval_id] = record
        return record

    async def get_user_pending_approvals(self, user_id: str) -> List[Dict[str, Any]]:
        now = time.time()
        results = []
        for rec in self.approvals_store.values():
            if rec["user_id"] == user_id:
                # Check 5-minute expiry
                if rec["status"] == "pending" and now > rec["expires_at"]:
                    rec["status"] = "expired"
                results.append(rec)
        return results

    async def get_approval_by_id(self, approval_id: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        rec = self.approvals_store.get(approval_id)
        if rec and rec["status"] == "pending" and now > rec["expires_at"]:
            rec["status"] = "expired"
        return rec

    async def resolve_approval(
        self,
        approval_id: str,
        decision: str,  # approve, edit, reject
        caller_user_id: str,
        edited_payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        rec = await self.get_approval_by_id(approval_id)
        if not rec:
            return {"error": "Approval request not found"}

        # Caller validation
        if rec["user_id"] != caller_user_id:
            return {"error": "Unauthorized: caller does not own this approval"}

        if rec["status"] == "expired":
            return {"error": "Approval request has expired (5-minute limit)"}

        if rec["status"] != "pending":
            return {"error": f"Approval is not pending (current status: {rec['status']})"}

        now = time.time()
        rec["status"] = decision
        rec["resolved_at"] = now
        if decision == "edit" and edited_payload:
            rec["arguments"].update(edited_payload)

        return {"status": decision, "record": rec}

    async def cancel_user_pending_approvals(self, user_id: str) -> int:
        """Emergency halt: cancels all pending approvals for a user and returns count."""
        now = time.time()
        count = 0
        for rec in self.approvals_store.values():
            if rec["user_id"] == user_id and rec["status"] == "pending":
                rec["status"] = "cancelled"
                rec["resolved_at"] = now
                count += 1
        return count

    async def insert_audit_log(self, record: Dict[str, Any]):
        """Insert-only audit log."""
        record["created_at"] = record.get("created_at") or time.time()
        record["id"] = record.get("id") or str(uuid.uuid4())
        self.audit_log_store.append(record)

    async def get_audit_logs(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        logs = self.audit_log_store
        if user_id:
            logs = [l for l in logs if l.get("user_id") == user_id]
        return logs[-limit:][::-1]

    async def get_idempotent_response(self, user_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        key = f"{user_id}:{idempotency_key}"
        return self.idempotency_store.get(key)

    async def save_idempotent_response(self, user_id: str, idempotency_key: str, response: Dict[str, Any]):
        key = f"{user_id}:{idempotency_key}"
        self.idempotency_store[key] = response

    async def get_webhook_dedupe(self, message_id: str) -> Optional[Dict[str, Any]]:
        return self.webhook_dedupe_store.get(message_id)

    async def save_webhook_dedupe(self, message_id: str, response: Dict[str, Any]):
        self.webhook_dedupe_store[message_id] = response


repository = DatabaseRepository()
