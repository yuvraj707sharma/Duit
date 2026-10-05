"""Mock Tools for testing and zero-dependency execution."""
from typing import Dict, Any, List
from backend.app.tools.base import BaseTool, ToolResult


class MockCalendarTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.events: Dict[str, Dict[str, Any]] = {}
        self.execution_count: int = 0

    async def execute(self, user_id: str, payload: Dict[str, Any]) -> ToolResult:
        idempotency_key = payload.get("idempotency_key")
        action = payload.get("action", "create")

        if idempotency_key and action in ("create", "reschedule", "cancel"):
            cached = self.get_cached_result(user_id, idempotency_key)
            if cached:
                return cached

        self.execution_count += 1
        event_id = payload.get("event_id", f"mock_evt_{self.execution_count}")
        
        event_record = {
            "user_id": user_id,
            "event_id": event_id,
            "title": payload.get("title", "Sync Meeting"),
            "start_time": payload.get("start_time") or payload.get("new_start_time", "2026-10-02T10:00:00Z"),
            "end_time": payload.get("end_time") or payload.get("new_end_time", "2026-10-02T11:00:00Z"),
            "attendees": payload.get("attendees", []),
            "status": "cancelled" if action == "cancel" else "active"
        }
        self.events[event_id] = event_record

        result = ToolResult(
            success=True,
            data=event_record
        )
        if idempotency_key:
            self.store_cached_result(user_id, idempotency_key, result)
        return result


class MockGmailTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.sent_emails: List[Dict[str, Any]] = []
        self.execution_count: int = 0

    async def execute(self, user_id: str, payload: Dict[str, Any]) -> ToolResult:
        idempotency_key = payload.get("idempotency_key")
        action = payload.get("action", "send")

        if idempotency_key and action == "send":
            cached = self.get_cached_result(user_id, idempotency_key)
            if cached:
                return cached

        self.execution_count += 1
        email_record = {
            "user_id": user_id,
            "email_id": f"mock_mail_{self.execution_count}",
            "recipient": payload.get("recipient", "user@example.com"),
            "subject": payload.get("subject", "No Subject"),
            "body": payload.get("body", ""),
            "status": "sent"
        }
        self.sent_emails.append(email_record)

        result = ToolResult(
            success=True,
            data=email_record
        )
        if idempotency_key:
            self.store_cached_result(user_id, idempotency_key, result)
        return result
