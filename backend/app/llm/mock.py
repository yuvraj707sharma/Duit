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
        elif intent == "open_app":
            app = "notepad"
            for candidate in ("notepad", "calculator", "terminal", "code", "browser", "slack", "spotify", "files"):
                if candidate in msg_lower:
                    app = candidate
                    break
            args = {"app_name": app}
        elif intent == "open_url":
            url_match = re.search(r"https?://[^\s]+", user_message)
            args = {"url": url_match.group(0) if url_match else "https://fastagent.dev"}
        elif intent == "create_note":
            args = {"title": "quick_note", "content": user_message}
        elif intent == "type_text":
            args = {"text": user_message}
        elif intent == "set_volume":
            vol_match = re.search(r"\b(\d{1,3})\b", user_message)
            args = {"level": int(vol_match.group(1)) if vol_match else 50}
        elif intent == "search_files":
            args = {"query": "invoice"}
        elif intent == "clear_history":
            args = {}
        else:
            args = {"raw_text": user_message}

        return ExtractionResult(
            success=True,
            arguments=args,
            raw_response="{}",
            tokens_used=42
        )

    async def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        prompt_lower = (system_prompt or "").lower()
        msg_lower = (user_message or "").lower()

        if "expense" in prompt_lower or "receipt" in prompt_lower:
            return (
                "🧾 *Expense Analysis*\n"
                "• *Category*: Business / Office\n"
                "• *Details*: Extracted from entry\n"
                "• *Raw Note*: " + user_message[:60] + "\n"
                "• *Status*: ✅ Logged & Categorized"
            )
        elif "action" in prompt_lower or "meeting" in prompt_lower or "staff" in prompt_lower:
            return (
                "📋 *Action Items Extracted*\n"
                "1. [Urgent] " + user_message[:50] + "\n"
                "2. [Normal] Confirm deliverables with team\n"
                "3. [Next Step] Track completion in sprint log"
            )
        elif "copywriter" in prompt_lower or "sales" in prompt_lower or "email" in prompt_lower:
            return (
                "💼 *Drafted Outreach Copy*\n"
                "Subject: Quick idea for your workflow\n\n"
                "Hi there,\n"
                f"I noticed your interest regarding '{user_message[:40]}...'. "
                "We help automate this in seconds without manual overhead.\n\n"
                "Would you be open to a 5-minute chat this Thursday?\n"
                "Best,\nFastAgent"
            )
        elif "debugger" in prompt_lower or "code" in prompt_lower or "software" in prompt_lower:
            return (
                "🛠️ *Code Review & Solution*\n"
                "• *Issue*: Syntax or logic exception detected in user snippet.\n"
                "• *Diagnosis*: Parameter verification needed.\n"
                "• *Fix*:\n```python\n# Cleaned fix\nresult = process_safe(data)\n```"
            )
        return f"✨ *Skill Execution Output*:\n{user_message}\n\n_Applied Prompt:_ {system_prompt[:60]}..."
