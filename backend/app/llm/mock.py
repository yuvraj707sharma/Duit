import re
import time as time_mod
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
    stop_words = {"me", "mine", "us", "him", "her", "them", "the", "a", "an", "my", "our", "tomorrow", "today", "yesterday", "team", "google", "whatsapp", "client", "friend", "colleague", "boss"}
    if person.lower() in stop_words:
        person = ""

    if person:
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
            email_match = re.search(r"[\w\.-]+@[\w\.-]+", user_message)
            recipient = email_match.group(0) if email_match else ("rahul@example.com" if "rahul" in msg_lower else "colleague@example.com")
            subject = "Quick Update"
            body = "Hi, replying to confirm as requested."

            about_match = re.search(r"(?:about|saying that|saying|regarding)\s+(.*)", user_message, re.IGNORECASE)
            if about_match:
                about_text = about_match.group(1).strip().rstrip(".! ")
                if any(w in about_text.lower() for w in ("meet", "meeting")):
                    subject = "Meeting Today"
                else:
                    subject = about_text[:40].capitalize()
                recipient_name = recipient.split("@")[0].split(".")[0].capitalize() if recipient else "there"
                clean_about = re.sub(r"\bmeet (?:him|her|them)\b", "meet you", about_text, flags=re.IGNORECASE)
                body = f"Hi {recipient_name},\n\nI wanted to reach out and let you know that {clean_about}.\n\nBest regards,"

            args = {
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "idempotency_key": f"mail_{int(time_mod.time()*1000)}"
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
            app_match = re.search(r"\b(?:open|launch|start)\s+(?:the\s+)?([a-zA-Z0-9_\-\.]+?)(?:\s+on\s+desktop|\s+app|\s+application|$)", user_message, re.IGNORECASE)
            app = app_match.group(1).strip() if app_match else "notepad"
            if app in ("calc", "calculator"):
                app = "calculator"
            elif app in ("vs code", "vscode"):
                app = "code"
            elif app in ("cmd", "powershell"):
                app = "terminal"
            elif app in ("explorer", "folder"):
                app = "files"

            draft_text = None
            if "notepad" in app.lower() and any(w in msg_lower for w in ("draft", "write", "message", "note")):
                if "dumb" in msg_lower or "ai" in msg_lower:
                    draft_text = (
                        "Are AI models getting dumber?\n"
                        "While models are getting larger, they often struggle with simple context and logic.\n"
                        "Hallucinations and over-confidence make basic tasks surprisingly brittle.\n"
                        "True intelligence requires genuine reasoning, not just pattern matching."
                    )
                else:
                    draft_text = "Quick draft notes:\n- Review project goals\n- Check system status\n- Next followups"

            args = {"app_name": app, "idempotency_key": f"app_{int(time_mod.time()*1000)}"}
            if draft_text:
                args["draft_text"] = draft_text
        elif intent == "open_url":
            url_match = re.search(r"https?://[^\s]+", user_message)
            if url_match:
                url = url_match.group(0)
            else:
                domain_match = re.search(r"\b([a-zA-Z0-9-]+\.(?:com|org|io|dev|in|net|co|app))\b", user_message, re.IGNORECASE)
                url = f"https://{domain_match.group(1)}" if domain_match else "https://fastagent.dev"

            browser = "default"
            if "edge" in msg_lower or "msedge" in msg_lower:
                browser = "edge"
            elif "chrome" in msg_lower:
                browser = "chrome"
            elif "firefox" in msg_lower:
                browser = "firefox"

            args = {"url": url, "browser": browser, "idempotency_key": f"url_{int(time_mod.time()*1000)}"}
        elif intent == "create_note":
            title = "Quick Note"
            content = ""
            m = re.search(r"(?:create note|take note|write note|make note|save note|write to file|create file)\s+(?:named\s+|called\s+|titled\s+)?([a-zA-Z0-9_\-\.]+)(?:\s+(?:with content|content|saying|text|having)\s+(.*))?", user_message, re.IGNORECASE)
            if m:
                title = m.group(1).strip()
                content = (m.group(2) or "").strip()
            if not content:
                content = re.sub(r"^(?:create note|take note|note down|write note|make a note|note:?|write to file|save file|create file|write file)\s*", "", user_message, flags=re.IGNORECASE).strip()
            args = {"title": title, "content": content or user_message, "idempotency_key": f"note_{int(time_mod.time()*1000)}"}
        elif intent == "type_text":
            text_to_type = re.sub(r"^(?:type text|type:?|write:?|now write a message on it|now write on it|write a message on it|now write|write a message)\s*", "", user_message, flags=re.IGNORECASE).strip()
            text_to_type = re.sub(r"\s+(?:into|in|on)\s+[a-zA-Z0-9_\-\.]+\s*$", "", text_to_type, flags=re.IGNORECASE).strip()
            if not text_to_type or text_to_type.lower() in ("on it", "message", "a message", "it"):
                text_to_type = (
                    "Artificial intelligence today often seems capable, yet it stumbles on basic context.\n"
                    "As models scale, prompt brittleness and hallucinations become more noticeable.\n"
                    "Without true reasoning and situational awareness, smart tech feels increasingly dumb."
                )
            args = {"text": text_to_type, "idempotency_key": f"type_{int(time_mod.time()*1000)}"}
        elif intent == "set_volume":
            vol_match = re.search(r"\b(\d{1,3})\b", user_message)
            args = {"level": int(vol_match.group(1)) if vol_match else 50, "idempotency_key": f"vol_{int(time_mod.time()*1000)}"}
        elif intent == "search_files":
            query = re.sub(r"^(?:search files?|find files?|search for|find|read files?|read notes?|read the file|open file|what is in file|show file|read my notes?)\s+(?:named\s+|for\s+)?", "", user_message, flags=re.IGNORECASE).strip()
            args = {"query": query or "note", "read_content": True, "idempotency_key": f"search_{int(time_mod.time()*1000)}"}
        elif intent == "clear_history":
            args = {"idempotency_key": f"clear_{int(time_mod.time()*1000)}"}
        elif intent == "shed_status":
            args = {"include_sessions": True}
        elif intent == "dispatch_coding_task":
            # Extract prompt and harness
            prompt = re.sub(r"^(?:start coding|dispatch coding|code with|shed code|run coding agent|dispatch to shed|ask claude to code|ask codex to code)\s*", "", user_message, flags=re.IGNORECASE).strip()
            harness = "auto"
            if "claude" in msg_lower:
                harness = "claude"
            elif "codex" in msg_lower:
                harness = "codex"
            elif "gemini" in msg_lower:
                harness = "gemini"
            elif "opencode" in msg_lower:
                harness = "opencode"
            args = {
                "prompt": prompt or user_message,
                "harness": harness,
                "idempotency_key": f"shed_{int(time_mod.time()*1000)}"
            }
        elif intent == "automate_cart":
            # Extract product name
            cleaned = re.sub(r"^(?:add to cart|cart me daal|cart add|add in cart|cart mein daalo|buy on amazon|order on amazon|add this to cart|add)\s*", "", user_message, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*(?:to cart|in cart|on amazon|from amazon|ko cart me daal do|ko cart mein daal do)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
            store = "flipkart" if "flipkart" in msg_lower else "amazon"
            args = {
                "product_name": cleaned or "Wireless Headphones",
                "store": store,
                "idempotency_key": f"cart_{int(time_mod.time()*1000)}"
            }
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
                "*Expense Analysis*\n"
                "• *Category*: Business / Office\n"
                "• *Details*: Extracted from entry\n"
                "• *Raw Note*: " + user_message[:60] + "\n"
                "• *Status*: Logged & Categorized"
            )
        elif "action" in prompt_lower or "meeting" in prompt_lower or "staff" in prompt_lower:
            return (
                "*Action Items Extracted*\n"
                "1. [Urgent] " + user_message[:50] + "\n"
                "2. [Normal] Confirm deliverables with team\n"
                "3. [Next Step] Track completion in sprint log"
            )
        elif "copywriter" in prompt_lower or "sales" in prompt_lower or "email" in prompt_lower:
            return (
                "*Drafted Outreach Copy*\n"
                "Subject: Quick idea for your workflow\n\n"
                "Hi there,\n"
                f"I noticed your interest regarding '{user_message[:40]}...'. "
                "We help automate this in seconds without manual overhead.\n\n"
                "Would you be open to a 5-minute chat this Thursday?\n"
                "Best,\nFastAgent"
            )
        elif "debugger" in prompt_lower or "code" in prompt_lower or "software" in prompt_lower:
            return (
                "*Code Review & Solution*\n"
                "• *Issue*: Syntax or logic exception detected in user snippet.\n"
                "• *Diagnosis*: Parameter verification needed.\n"
                "• *Fix*:\n```python\n# Cleaned fix\nresult = process_safe(data)\n```"
            )
        return f"*Skill Execution Output*:\n{user_message}\n\n_Applied Prompt:_ {system_prompt[:60]}..."
