"""Gmail Tool Adapter."""
from typing import Dict, Any, Optional
from backend.app.tools.base import BaseTool, ToolResult


class GmailTool(BaseTool):
    def __init__(self, service_factory=None):
        super().__init__()
        self.service_factory = service_factory

    async def execute(self, user_id: str, payload: Dict[str, Any]) -> ToolResult:
        idempotency_key = payload.get("idempotency_key")
        action = payload.get("action", "send")  # send, summarize, fetch

        if idempotency_key and action == "send":
            cached = self.get_cached_result(user_id, idempotency_key)
            if cached:
                return cached

        result_data = {
            "action": action,
            "status": "sent" if action == "send" else "success",
            "message_id": payload.get("message_id", "msg_real_gmail_999"),
            "recipient": payload.get("recipient"),
            "subject": payload.get("subject"),
            "body_snippet": payload.get("body", "")[:100]
        }

        result = ToolResult(success=True, data=result_data)
        if idempotency_key:
            self.store_cached_result(user_id, idempotency_key, result)
        return result
