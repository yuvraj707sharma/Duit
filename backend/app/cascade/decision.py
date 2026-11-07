"""Stage 2: Fast Decision Layer (Laya Multilingual Router / Service)."""
import re
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx
from pydantic import BaseModel
from backend.app.config import settings
from backend.app.metrics import metrics_collector

logger = logging.getLogger(__name__)


class DecisionOutput(BaseModel):
    intent: str
    risk: str  # low, medium, high
    needs_confirmation: bool
    confidence: float
    detected_language: str
    model_used: str
    reasoning_tag: str


class DecisionModel(ABC):
    @abstractmethod
    async def decide(self, message: str, context: Optional[Dict[str, Any]] = None) -> DecisionOutput:
        """Classifies intent, risk, and needs_confirmation with calibrated confidence."""
        pass


from backend.app.policy.confirmations import INTENT_RISK_MAP


class LayaDecisionModel(DecisionModel):
    """Calls laya-serve HTTP service or native Laya router asking only the intent question."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.LAYA_BASE_URL).rstrip("/")

    async def decide(self, message: str, context: Optional[Dict[str, Any]] = None) -> DecisionOutput:
        # Ask ONLY the intent question; risk is derived in code from INTENT_RISK_MAP
        questions = {
            "intent": {
                "type": "choice",
                "instructions": "Classify the user intent into one of the available choices.",
                "criteria": {
                    "schedule_meeting": "Create a new meeting or calendar event",
                    "reschedule_meeting": "Move, change time, or reschedule an existing meeting",
                    "cancel_meeting": "Delete or cancel a meeting",
                    "check_calendar": "Check schedule, availability, or free slots",
                    "reply_email": "Reply to or answer an existing email",
                    "summarize_email": "Summarize unread emails or inbox",
                    "send_email": "Draft or send a new email",
                    "book_something": "Book a ticket, restaurant, or ride",
                    "open_app": "Open or launch desktop application on PC",
                    "open_url": "Open webpage or URL on desktop browser",
                    "create_note": "Create, take or save a desktop note",
                    "search_files": "Search or find files on desktop computer",
                    "shed_status": "Check Shed remote coding agent status and harnesses",
                    "dispatch_coding_task": "Dispatch or start a coding task on Claude, Codex, or Gemini via Shed",
                    "automate_cart": "Search e-commerce site and add product to shopping cart",
                    "other": "General conversation or other requests"
                }
            }
        }
        payload = {
            "state": message,
            "questions": questions,
            "model": "convaiinnovations/laya-multilingual"
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(f"{self.base_url}/v1/systemone", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    answers = data.get("answers", {})
                    intent_ans = answers.get("intent", {})

                    # Strict confidence parsing: no default float invention
                    if "confidence" not in intent_ans or not isinstance(intent_ans["confidence"], (int, float)):
                        raise ValueError("Laya response missing valid numerical confidence score in intent answer.")

                    intent = intent_ans.get("choice")
                    if not intent:
                        raise ValueError("Laya response missing intent choice.")

                    conf = float(intent_ans["confidence"])
                    
                    # Derive risk and confirmation in code from INTENT_RISK_MAP
                    risk, needs_conf_base = INTENT_RISK_MAP.get(intent, ("low", False))
                    needs_conf = needs_conf_base or risk in ("medium", "high") or conf < settings.LAYA_MIN_CONFIDENCE_THRESHOLD

                    routing_info = data.get("routing", {})
                    checkpoint_used = routing_info.get("model", "multilingual")

                    return DecisionOutput(
                        intent=intent,
                        risk=risk,
                        needs_confirmation=needs_conf,
                        confidence=conf,
                        detected_language=routing_info.get("reason", "multilingual"),
                        model_used=f"laya-{checkpoint_used}",
                        reasoning_tag=f"laya_checkpoint:{checkpoint_used}"
                    )
                else:
                    raise RuntimeError(f"Laya server returned HTTP {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Laya inference error or timeout: {e}")
            metrics_collector.record_decision_error()

            # Safe fail-closed gate: Return forced confirmation decision with zero confidence and high risk
            return DecisionOutput(
                intent="other",
                risk="high",
                needs_confirmation=True,
                confidence=0.0,
                detected_language="unknown",
                model_used="laya-error-fallback",
                reasoning_tag=f"laya_error_forced_confirmation: {type(e).__name__}"
            )


class MockDecisionModel(DecisionModel):
    """Accurate offline decision model covering English, Hindi, Hinglish, and Negation."""

    async def decide(self, message: str, context: Optional[Dict[str, Any]] = None) -> DecisionOutput:
        msg = message.strip().lower()

        # 1. Explicit negation patterns (e.g. "don't cancel X, but move/reschedule Y")
        if "don't cancel" in msg or "do not cancel" in msg or "cancel mat" in msg:
            if any(w in msg for w in ("move", "reschedule", "shift", "change time", "badal", "badhao", "aage")):
                return DecisionOutput(
                    intent="reschedule_meeting",
                    risk="medium",
                    needs_confirmation=True,
                    confidence=0.94,
                    detected_language="hi-Latn" if any(w in msg for w in ("karo", "mat", "badhao")) else "en",
                    model_used="mock-laya-router",
                    reasoning_tag="negation_aware_reschedule"
                )

        # 2. Reschedule meeting
        if any(w in msg for w in ("move my", "reschedule", "shift to", "postpone", "prepone", "change time", "aage badhao", "shift kar do")):
            return DecisionOutput(
                intent="reschedule_meeting",
                risk="medium",
                needs_confirmation=True,
                confidence=0.95,
                detected_language="hi-Latn" if any(w in msg for w in ("badhao", "kar do")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="reschedule_keyword"
            )

        # 3. Cancel meeting
        if any(w in msg for w in ("cancel meeting", "cancel my", "cancel tomorrow", "delete event", "cancel karo", "meeting hatao")):
            return DecisionOutput(
                intent="cancel_meeting",
                risk="high",
                needs_confirmation=True,
                confidence=0.96,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="cancel_keyword"
            )

        # Explicit file search / read keywords (checked before calendar/schedule keywords)
        if any(w in msg for w in (
            "search files", "search file", "find files", "find file", "file search",
            "read file", "read the file", "open file", "what is in file", "show file",
            "udhaar sheet", "laptop se bhejo", "laptop se send"
        )):
            return DecisionOutput(
                intent="search_files",
                risk="low",
                needs_confirmation=False,
                confidence=0.94,
                detected_language="hi-Latn" if any(w in msg for w in ("sheet", "bhejo", "laptop se")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="desktop_search_and_read_files"
            )

        # Check calendar read queries if explicit read words present
        if any(w in msg for w in (
            "check calendar", "view calendar", "show calendar", "is my calendar",
            "what is on my", "what's on my", "am i free", "free today", "free tomorrow",
            "schedule kya hai", "aaj ka schedule", "meetings today", "any meetings",
            "check meetings", "meetings scheduled", "have we got any meetings", "what meetings"
        )):
            return DecisionOutput(
                intent="check_calendar",
                risk="low",
                needs_confirmation=False,
                confidence=0.98,
                detected_language="hi-Latn" if any(w in msg for w in ("kya hai", "aaj")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="calendar_read_query"
            )

        # 4. Schedule meeting (English / Hindi / Hinglish)
        meeting_terms = (
            "schedule", "set the meeting", "set meeting", "set up meeting", "book a slot", "book slot",
            "meeting fix kar do", "meeting rakh do", "rakh do", "meet with", "appointment",
            "arrange a meeting", "catchup", "sync with", "call with", "put it on the calendar",
            "put on the calendar", "add to the calendar", "add to calendar", "block my calendar",
            "block calendar", "calendar me daal", "calendar pe daal", "on the calendar",
            "book on the calendar", "book site visit", "book visit", "book a visit"
        )
        if any(w in msg for w in meeting_terms):
            return DecisionOutput(
                intent="schedule_meeting",
                risk="medium",
                needs_confirmation=True,
                confidence=0.94,
                detected_language="hi-Latn" if any(w in msg for w in ("kar do", "rakh", "baje", "ke saath", "daal")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="schedule_keyword"
            )

        # 6. Email replies / sends / summaries
        email_terms = ("email", "emails", "mail", "mails", "inbox", "gmail")
        has_email = any(term in msg for term in email_terms)

        if any(w in msg for w in ("reply yes", "reply to", "email back", "mail ka jawab", "reply to email", "reply to mail")):
            return DecisionOutput(
                intent="reply_email",
                risk="medium",
                needs_confirmation=True,
                confidence=0.92,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="email_reply_keyword"
            )

        has_email_addr = bool(re.search(r"[\w\.-]+@[\w\.-]+", msg))
        if (has_email_addr and any(w in msg for w in ("write", "send", "mail", "email", "draft", "compose", "to"))) or \
           any(w in msg for w in (
               "send email", "send an email", "send this to", "send to", "forward to", "forward all",
               "mail bhej do", "email likh do", "draft email", "compose email", "write mail", "write email",
               "write a mail", "write an email", "mail to", "email to", "send mail"
           )):
            return DecisionOutput(
                intent="send_email",
                risk="high",
                needs_confirmation=True,
                confidence=0.95,
                detected_language="hi-Latn" if any(w in msg for w in ("bhej do", "likh do")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="email_send_keyword"
            )

        is_chat_summary = any(w in msg for w in ("whatsapp", "chat", "chats", "text", "texts", "conversation", "conversations"))
        if not is_chat_summary and ((has_email and any(w in msg for w in (
            "summarize", "summary", "summarise", "unread", "recent", "latest",
            "check", "read", "fetch", "get", "give me", "show", "batao", "kya aaya", "kya aya", "list"
        ))) or any(w in msg for w in ("summarize email", "unread emails", "inbox summary", "emails batao", "summarize my emails", "summarize my mails", "recent mails", "recent emails"))):
            return DecisionOutput(
                intent="summarize_email",
                risk="low",
                needs_confirmation=False,
                confidence=0.95,
                detected_language="hi-Latn" if any(w in msg for w in ("batao", "kya aaya", "kya aya")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="email_summary_keyword"
            )

        if any(w in msg for w in ("book an uber", "book a ride", "book flight", "book ticket", "book an")):
            return DecisionOutput(
                intent="book_something",
                risk="high",
                needs_confirmation=True,
                confidence=0.92,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="booking_keyword"
            )

        # 7. Desktop Intents (App execution, browser URLs, files, notes, typing, volume)
        clean_desktop_msg = re.sub(r"[.!?,]+$", "", msg.strip())
        app_match = re.search(r"\b(?:open|launch|start|run)\s+(?:the\s+)?([a-zA-Z0-9_\-\. ]+?)(?:\s+on\s+(?:my\s+)?(?:desktop|laptop|pc|computer)|\s+app|\s+application|$)", clean_desktop_msg, re.IGNORECASE)
        has_app_excluded = any(w in msg for w in ("url", "site", "website", "link", "http", "cart", "email", "mail", "meeting", "slot", "calendar", "files", ".com", ".org", ".io", ".dev", ".in", ".net", "browse", "explore"))
        if not has_app_excluded and re.search(r"\bnotes?\b", msg) and not re.search(r"\bnotepads?\b", msg):
            has_app_excluded = True
        if app_match and not has_app_excluded:
            return DecisionOutput(
                intent="open_app",
                risk="medium",
                needs_confirmation=True,
                confidence=0.95,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="dynamic_desktop_open_app"
            )

        if msg.startswith("type ") or any(w in msg for w in (
            "now write", "type text", "type this", "type on it", "write a message", "write on it",
            "write message", "type on screen", "type into", "type it", "write it", "type something",
            "write something", "type here", "write here"
        )):
            return DecisionOutput(
                intent="type_text",
                risk="medium",
                needs_confirmation=True,
                confidence=0.95,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="desktop_type_text"
            )

        has_url_pattern = bool(re.search(r"https?://|\b[a-zA-Z0-9-]+\.(?:com|org|io|dev|in|net|co|app)\b", msg))
        if any(w in msg for w in (
            "open url", "open link", "open site", "open website", "explore site", "explore website",
            "explore on browser", "explore in browser", "explore edge", "in edge", "on edge",
            "browse to", "navigate to", "take me to", "visit site", "visit link", "khol do browser",
            "khol do edge", "open in edge", "open in browser", "open on edge", "open on browser",
            "browse edge", "explore on edge"
        )) or (has_url_pattern and any(w in msg for w in ("open", "explore", "browse", "visit", "navigate", "go to", "load", "khol", "show", "take me"))):
            return DecisionOutput(
                intent="open_url",
                risk="low",
                needs_confirmation=False,
                confidence=0.95,
                detected_language="hi-Latn" if any(w in msg for w in ("khol", "karo", "pe")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="desktop_open_url"
            )

        if any(w in msg for w in (
            "search files", "search file", "find files", "find file", "file search",
            "read file", "read note", "read the file", "open file", "what is in file", "show file",
            "read my notes", "read my note", "read notes"
        )):
            return DecisionOutput(
                intent="search_files",
                risk="low",
                needs_confirmation=False,
                confidence=0.94,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="desktop_search_and_read_files"
            )

        if any(w in msg for w in (
            "create note", "take note", "note down", "write note", "make a note", "save note",
            "write to file", "save file", "create file", "write file"
        )):
            return DecisionOutput(
                intent="create_note",
                risk="low",
                needs_confirmation=False,
                confidence=0.94,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="desktop_create_note"
            )

        if any(w in msg for w in ("set volume", "change volume", "volume to", "adjust volume", "mute volume")):
            return DecisionOutput(
                intent="set_volume",
                risk="low",
                needs_confirmation=False,
                confidence=0.95,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="desktop_set_volume"
            )

        # 8. Shed Remote Coding Agent Intents
        if any(w in msg for w in ("shed status", "shed info", "coding agents", "active harnesses", "agent status", "harness health", "list coding", "coding sessions", "shed check")) or msg == "shed":
            return DecisionOutput(
                intent="shed_status",
                risk="low",
                needs_confirmation=False,
                confidence=0.98,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="shed_status_query"
            )

        if any(w in msg for w in ("start coding", "dispatch coding", "code with", "shed code", "run coding agent", "dispatch to shed", "ask claude to code", "ask codex to code")):
            return DecisionOutput(
                intent="dispatch_coding_task",
                risk="medium",
                needs_confirmation=True,
                confidence=0.95,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="shed_dispatch_coding"
            )

        # 9. Autonomous Browser & Shopping Cart
        if any(w in msg for w in ("to cart", "in cart", "cart me", "cart mein", "buy on", "order on", "add to basket")) or (("add" in msg or "daal" in msg or "put" in msg) and "cart" in msg):
            return DecisionOutput(
                intent="automate_cart",
                risk="medium",
                needs_confirmation=True,
                confidence=0.95,
                detected_language="hi-Latn" if any(w in msg for w in ("daal", "mein")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="browser_automate_cart"
            )

        # Default / low confidence fallback
        return DecisionOutput(
            intent="other",
            risk="low",
            needs_confirmation=False,
            confidence=0.60,
            detected_language="en",
            model_used="mock-laya-router",
            reasoning_tag="fallback_other"
        )
