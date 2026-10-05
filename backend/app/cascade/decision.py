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

        # 4. Check calendar / availability (evaluate before schedule creation)
        if any(w in msg for w in ("calendar", "what is on my", "what's on my", "schedule kya hai", "aaj ka schedule", "check calendar", "my schedule", "free today", "free tomorrow", "availability", "meetings today", "am i free")):
            return DecisionOutput(
                intent="check_calendar",
                risk="low",
                needs_confirmation=False,
                confidence=0.98,
                detected_language="hi-Latn" if any(w in msg for w in ("kya hai", "aaj")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="calendar_read_query"
            )

        # 5. Schedule meeting (English / Hindi / Hinglish)
        if any(w in msg for w in ("schedule", "set up meeting", "book a slot", "meeting fix kar do", "rakh do", "meet with")):
            return DecisionOutput(
                intent="schedule_meeting",
                risk="medium",
                needs_confirmation=True,
                confidence=0.93,
                detected_language="hi-Latn" if any(w in msg for w in ("kar do", "rakh", "baje")) else "en",
                model_used="mock-laya-router",
                reasoning_tag="schedule_keyword"
            )

        # 6. Email replies / sends / summaries
        if any(w in msg for w in ("reply yes", "reply to", "email back", "mail ka jawab")):
            return DecisionOutput(
                intent="reply_email",
                risk="medium",
                needs_confirmation=True,
                confidence=0.92,
                detected_language="en",
                model_used="mock-laya-router",
                reasoning_tag="email_reply_keyword"
            )

        if any(w in msg for w in ("send email", "send an email", "send this to", "send to", "forward to", "forward all", "mail bhej do", "email likh do")):
            return DecisionOutput(
                intent="send_email",
                risk="high",
                needs_confirmation=True,
                confidence=0.95,
                detected_language="hi-Latn" if "bhej do" in msg else "en",
                model_used="mock-laya-router",
                reasoning_tag="email_send_keyword"
            )

        if any(w in msg for w in ("summarize email", "unread emails", "inbox summary", "emails batao", "summarize my")):
            return DecisionOutput(
                intent="summarize_email",
                risk="low",
                needs_confirmation=False,
                confidence=0.94,
                detected_language="en",
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
