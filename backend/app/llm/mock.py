"""Mock LLM Provider for deterministic argument extraction in tests and offline development."""
import re
from typing import Dict, Any, Optional
from backend.app.llm.base import LLMProvider, ExtractionResult


class MockLLMProvider(LLMProvider):
    async def extract_arguments(
        self,
        user_message: str,
        intent: str,
        schema: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExtractionResult:
        msg_lower = user_message.lower()
        args: Dict[str, Any] = {}

        if intent in ("schedule_meeting", "create_calendar_event"):
            args = {
                "title": "Discussion Meeting",
                "start_time": "2026-10-02T10:00:00Z",
                "end_time": "2026-10-02T11:00:00Z",
                "attendees": ["rahul@example.com"] if "rahul" in msg_lower else []
            }
        elif intent in ("reschedule_meeting", "reschedule_calendar_event"):
            args = {
                "event_id": "mock_event_sync_101",
                "new_start_time": "2026-10-02T16:00:00Z",
                "new_end_time": "2026-10-02T17:00:00Z"
            }
        elif intent in ("cancel_meeting", "cancel_calendar_event"):
            args = {
                "event_id": "mock_event_sync_101",
                "reason": "User requested cancellation"
            }
        elif intent in ("send_email", "reply_email"):
            # Check for emails in string
            email_match = re.search(r"[\w\.-]+@[\w\.-]+", user_message)
            recipient = email_match.group(0) if email_match else ("rahul@example.com" if "rahul" in msg_lower else "colleague@example.com")
            args = {
                "recipient": recipient,
                "subject": "Quick Update",
                "body": "Hi, replying to confirm as requested."
            }
        elif intent == "check_calendar":
            args = {
                "time_min": "2026-10-02T00:00:00Z",
                "time_max": "2026-10-02T23:59:59Z"
            }
        elif intent == "summarize_email":
            args = {
                "query": "is:unread",
                "max_results": 5
            }
        else:
            args = {"raw_text": user_message}

        return ExtractionResult(
            success=True,
            arguments=args,
            raw_response="{}",
            tokens_used=42
        )
