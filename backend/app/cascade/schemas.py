"""Schema Loader: maps intents to schemas defined in contracts/tool_calls.json."""
import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

_TOOL_CALLS_CACHE: Dict[str, Any] = {}

INTENT_TOOL_MAPPING = {
    "send_email": "SendEmail",
    "reply_email": "SendEmail",
    "schedule_meeting": "CreateCalendarEvent",
    "create_calendar_event": "CreateCalendarEvent",
    "reschedule_meeting": "RescheduleCalendarEvent",
    "reschedule_calendar_event": "RescheduleCalendarEvent",
    "cancel_meeting": "CancelCalendarEvent",
    "cancel_calendar_event": "CancelCalendarEvent",
    "check_calendar": "ListCalendarEvents",
    "summarize_email": "FetchEmails",
    "open_app": "OpenApp",
    "open_url": "OpenUrl",
    "create_note": "CreateNote",
    "type_text": "TypeText",
    "set_volume": "SetVolume",
    "search_files": "SearchFiles",
    "clear_history": "ClearHistory",
    "shed_status": "ShedStatus",
    "dispatch_coding_task": "DispatchCodingTask",
    "automate_cart": "AutomateCart",
    "whatsapp_search": "SearchWhatsAppArchive",
    "list_browser_profiles": "ListBrowserProfiles",
}


def get_schema_for_intent(intent: str) -> Dict[str, Any]:
    """Retrieves JSON schema from contracts/tool_calls.json for a given intent."""
    global _TOOL_CALLS_CACHE
    if not _TOOL_CALLS_CACHE:
        try:
            # Look relative to current file (backend/app/cascade -> contracts/tool_calls.json)
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            contracts_path = os.path.join(base_dir, "contracts", "tool_calls.json")
            if os.path.exists(contracts_path):
                with open(contracts_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    _TOOL_CALLS_CACHE = data.get("definitions", {})
        except Exception as ex:
            logger.warning("Failed to load contracts/tool_calls.json: %s", ex)
            _TOOL_CALLS_CACHE = {}

    def_name = INTENT_TOOL_MAPPING.get(intent)
    if def_name and def_name in _TOOL_CALLS_CACHE:
        return _TOOL_CALLS_CACHE[def_name]
    return {}

