"""Policy Confirmation Rules and Full Draft Body Formatter."""
from typing import Dict, Any, List
from pydantic import BaseModel


class PolicyEvaluation(BaseModel):
    allowed: bool
    requires_confirmation: bool
    risk_level: str  # low, medium, high
    reasoning: str
    suggested_prompt: str = ""


# Default risk mappings for v1 intents
INTENT_RISK_MAP = {
    "check_calendar": ("low", False),
    "summarize_email": ("low", False),
    "schedule_meeting": ("medium", True),
    "reschedule_meeting": ("medium", True),
    "cancel_meeting": ("high", True),
    "send_email": ("high", True),
    "reply_email": ("medium", True),
    "book_something": ("high", True),
    "open_app": ("medium", True),
    "open_url": ("low", False),
    "create_note": ("low", False),
    "type_text": ("medium", True),
    "set_volume": ("low", False),
    "search_files": ("low", False),
    "clear_history": ("low", True),
    "shed_status": ("low", False),
    "dispatch_coding_task": ("medium", True),
    "automate_cart": ("medium", True),
    "whatsapp_search": ("low", False),
    "other": ("low", False)
}


def build_confirmation_prompt(intent: str, args: Dict[str, Any]) -> str:
    """Formats human-readable confirmation prompt with full draft body and parameters."""
    if intent in ("send_email", "reply_email"):
        recipient = args.get("recipient", "unknown")
        subject = args.get("subject", "No subject")
        body = args.get("body", "(Empty body)")
        return (
            f"Send email to *{recipient}*?\n"
            f"- *Subject:* {subject}\n"
            f"- *Body:*\n{body}\n\n"
            f"_Reply *yes* to send, or *no* to cancel._"
        )
    elif intent == "schedule_meeting":
        title = args.get("title", "Meeting")
        start = args.get("start_time", "specified time")
        end = args.get("end_time", "")
        attendees = ", ".join(args.get("attendees", [])) or "None"
        desc = args.get("description", "(No description)")
        time_str = f"{start} to {end}" if end else start
        return (
            f"Schedule meeting *'{title}'*?\n"
            f"- *Time:* {time_str}\n"
            f"- *Attendees:* {attendees}\n"
            f"- *Description:* {desc}\n\n"
            f"_Reply *yes* to confirm & sync to Google Calendar, or *no* to cancel._"
        )
    elif intent == "reschedule_meeting":
        event_id = args.get("event_id", "meeting")
        new_start = args.get("new_start_time", "new time")
        new_end = args.get("new_end_time", "")
        time_str = f"{new_start} to {new_end}" if new_end else new_start
        return f"Reschedule meeting *'{event_id}'* to *{time_str}*?\n\n_Reply *yes* to confirm, or *no* to cancel._"
    elif intent == "cancel_meeting":
        event_id = args.get("event_id", "meeting")
        reason = args.get("reason", "None provided")
        query_text = args.get("query_text", "")
        query_line = f"\n- *Original Request:* \"{query_text}\"" if query_text else ""
        return f"Are you sure you want to CANCEL meeting *'{event_id}'*?{query_line}\n(Reason: {reason})\n\n_Reply *yes* to confirm, or *no* to cancel._"
    elif intent == "book_something":
        details = args.get("details", args.get("raw_text", "booking request"))
        return f"Confirm booking for: *{details}*?\n\n_Reply *yes* to proceed, or *no* to cancel._"
    elif intent == "open_app":
        app_name = args.get("app_name", "app")
        draft = args.get("draft_text", "")
        if draft:
            preview = draft[:100] + ("..." if len(draft) > 100 else "")
            return (
                f"Open application *'{app_name}'* on your desktop and initialize draft?\n"
                f"- *Draft:*\n{preview}\n\n"
                f"_Reply *yes* to launch, or *no* to cancel._"
            )
        return (
            f"Open application *'{app_name}'* on your desktop?\n\n"
            f"_Reply *yes* to launch, or *no* to cancel._"
        )
    elif intent == "open_url":
        url = args.get("url", "website")
        return (
            f"Open link *'{url}'* in your desktop browser?\n\n"
            f"_Reply *yes* to open, or *no* to cancel._"
        )
    elif intent == "type_text":
        text = args.get("text", "")
        preview = text[:80] + ("..." if len(text) > 80 else "")
        return (
            f"Type text into the active window on your desktop?\n"
            f"- *Text:* \"{preview}\"\n\n"
            f"_Reply *yes* to proceed, or *no* to cancel._"
        )
    elif intent == "clear_history":
        return "Clear all stored desktop operation history and reset encrypted context?\n\n_Reply *yes* to confirm, or *no* to cancel._"
    elif intent == "dispatch_coding_task":
        prompt = args.get("prompt", "task")
        harness = args.get("harness", "auto")
        return (
            f"Dispatch coding task to Shed agent ({harness})?\n"
            f"- *Prompt:* {prompt}\n\n"
            f"_Reply *yes* to start agent, or *no* to cancel._"
        )
    elif intent == "automate_cart":
        product = args.get("product_name", "item")
        store = args.get("store", "Amazon")
        return (
            f"Search and add to cart on {store.capitalize()}?\n"
            f"- *Item:* {product}\n\n"
            f"_Reply *yes* to add to cart, or *no* to cancel._"
        )
    return "Confirm execution of this action?\n\n_Reply *yes* to proceed, or *no* to cancel._"
