import re
from datetime import datetime, timedelta, time
from typing import Dict, Any, Optional, List
from backend.app.llm.base import LLMProvider, ExtractionResult


def _parse_meeting_details(user_message: str) -> Dict[str, Any]:
    msg_lower = user_message.lower()
    now = datetime.now()

    # 1. Attendees & Person extraction
    emails = re.findall(r"[\w\.-]+@[\w\.-]+", user_message)
    attendees: List[str] = list(emails)

    person_match = re.search(r"\b(?:with|and|of mine with)\s+([A-Za-z]+)", user_message, re.IGNORECASE)
    person = person_match.group(1).strip() if person_match else ""
    stop_words = {"me", "mine", "us", "him", "her", "them", "the", "a", "an", "my", "our", "tomorrow", "today", "yesterday", "team", "google"}
    if person.lower() in stop_words:
        person = ""

    if person:
        person_email = f"{person.lower()}@gmail.com"
        if person_email not in attendees and not emails:
            attendees.append(person_email)
        title = f"Meeting with {person.title()}"
    elif "sync" in msg_lower:
        title = "Team Sync"
    elif "standup" in msg_lower:
        title = "Daily Standup"
    elif "catchup" in msg_lower or "catch up" in msg_lower:
        title = "Catch-up Meeting"
    else:
        title = "Discussion Meeting"

    # 2. Date parsing
    target_date = now.date()
    if "day after tomorrow" in msg_lower or "parso" in msg_lower:
        target_date = now.date() + timedelta(days=2)
    elif "tomorrow" in msg_lower or "kal" in msg_lower:
        target_date = now.date() + timedelta(days=1)
    elif "today" in msg_lower or "aaj" in msg_lower:
        target_date = now.date()
    else:
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        matched_day = None
        for i, w in enumerate(weekdays):
            if w in msg_lower:
                matched_day = i
                break
        if matched_day is not None:
            days_ahead = (matched_day - now.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            target_date = now.date() + timedelta(days=days_ahead)
        elif now.hour >= 18:
            target_date = now.date() + timedelta(days=1)

    # 3. Time parsing
    hour = 16  # Default 4 PM
    minute = 0
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", msg_lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        meridiem = time_match.group(3).lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    else:
        time_match_2 = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\b", msg_lower)
        if time_match_2:
            hour = int(time_match_2.group(1))
            minute = int(time_match_2.group(2)) if time_match_2.group(2) else 0
            if hour <= 6:
                hour += 12
        else:
            time_match_3 = re.search(r"\b(\d{1,2})\s*baje\b", msg_lower)
            if time_match_3:
                hour = int(time_match_3.group(1))
                if hour <= 6:
                    hour += 12

    start_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute)
    end_dt = start_dt + timedelta(hours=1)

    return {
        "title": title,
        "start_time": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attendees": attendees
    }


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
            args = _parse_meeting_details(user_message)
        elif intent in ("reschedule_meeting", "reschedule_calendar_event"):
            details = _parse_meeting_details(user_message)
            args = {
                "event_id": "mock_event_sync_101",
                "new_start_time": details["start_time"],
                "new_end_time": details["end_time"]
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
