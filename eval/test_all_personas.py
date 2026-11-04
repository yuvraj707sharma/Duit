"""Evaluation Suite: Testing FastAgent across all 12 Personas and Core Skills.

Skills Covered:
  [CAL]   Calendar (schedule, reschedule, cancel, check)
  [MAIL]  Gmail (draft, send with confirmation, search/summarize)
  [VOICE] Voice STT (Hinglish/Hindi/English)
  [APP]   Open & verify desktop apps (universal resolver)
  [FILE]  Find, read, and create files
  [SHOT]  Screenshot proof
  [BRIEF] Morning briefing synthesis
  [RUN]   Shed coding task dispatch & status
"""
import asyncio
import time
import os
import pytest
from unittest.mock import patch, MagicMock

from backend.app.cascade.orchestrator import CascadeOrchestrator
from backend.app.desktop.skills import skill_executor
from backend.app.desktop.presence import presence_manager
from backend.app.channels.mock import MockChannel
from backend.app.tools.mock import MockCalendarTool, MockGmailTool
from backend.app.policy.engine import policy_engine
from backend.app.desktop.voice_stt import voice_stt_engine


PERSONAS = [
    {
        "id": 1,
        "name": "Restaurant Owner (Meera)",
        "language": "Hinglish",
        "prompt": "Kal ke liye supplier ko email bhejo ki 20kg paneer chahiye, aur Friday 3 baje chef ke saath meeting rakh do.",
        "expected_intent": ("send_email", "schedule_meeting"),
        "requires_confirmation": True,
        "risk_level": "high",
        "skill_tags": ["[VOICE]", "[MAIL]", "[CAL]"]
    },
    {
        "id": 2,
        "name": "School Teacher (Mr. Verma)",
        "language": "English",
        "prompt": "Remind me to email parents about Friday's PTM and put it on the calendar.",
        "expected_intent": "schedule_meeting",
        "requires_confirmation": True,
        "risk_level": "medium",
        "skill_tags": ["[CAL]", "[MAIL]"]
    },
    {
        "id": 3,
        "name": "College Student (Aarav)",
        "language": "English",
        "prompt": "Create note OS_Lab_Notes with content submit kernel assignment by 9 PM.",
        "expected_intent": "create_note",
        "requires_confirmation": False,
        "risk_level": "low",
        "skill_tags": ["[FILE]"]
    },
    {
        "id": 4,
        "name": "Senior Citizen (Dadaji)",
        "language": "Hindi/Hinglish",
        "prompt": "Beta ke saath kal shaam 5 baje call rakh do.",
        "expected_intent": "schedule_meeting",
        "requires_confirmation": True,
        "risk_level": "medium",
        "skill_tags": ["[VOICE]", "[CAL]"]
    },
    {
        "id": 5,
        "name": "Startup CEO",
        "language": "English",
        "prompt": "Summarize my unread emails and briefing for today.",
        "expected_intent": "summarize_email",
        "requires_confirmation": False,
        "risk_level": "low",
        "skill_tags": ["[BRIEF]", "[MAIL]"]
    },
    {
        "id": 6,
        "name": "Software Developer",
        "language": "English",
        "prompt": "Check Shed status on my workstation.",
        "expected_intent": "shed_status",
        "requires_confirmation": False,
        "risk_level": "low",
        "skill_tags": ["[RUN]"]
    },
    {
        "id": 7,
        "name": "Sales Director",
        "language": "English",
        "prompt": "Explore youtube.com in edge browser.",
        "expected_intent": "open_url",
        "requires_confirmation": False,
        "risk_level": "low",
        "skill_tags": ["[APP]", "[SHOT]"]
    },
    {
        "id": 8,
        "name": "Freelancer / Agency Owner",
        "language": "English",
        "prompt": "Check my unread emails for client quotes.",
        "expected_intent": "summarize_email",
        "requires_confirmation": False,
        "risk_level": "low",
        "skill_tags": ["[MAIL]"]
    },
    {
        "id": 9,
        "name": "Doctor / Clinic Receptionist",
        "language": "English",
        "prompt": "Reschedule appointment with Dr. Sharma to 2 PM tomorrow.",
        "expected_intent": "reschedule_meeting",
        "requires_confirmation": True,
        "risk_level": "medium",
        "skill_tags": ["[CAL]"]
    },
    {
        "id": 10,
        "name": "Shopkeeper (Diwali Sale)",
        "language": "Hinglish",
        "prompt": "Open invoice template on desktop.",
        "expected_intent": "open_app",
        "requires_confirmation": True,
        "risk_level": "medium",
        "skill_tags": ["[VOICE]", "[APP]", "[SHOT]"]
    },
    {
        "id": 11,
        "name": "Field Worker (Laptop Offline Check)",
        "language": "English",
        "prompt": "Open notepad on desktop.",
        "expected_intent": "open_app",
        "test_offline": True,
        "expected_reply": "laptop offline",
        "skill_tags": ["[APP]"]
    },
    {
        "id": 12,
        "name": "Content Creator / Designer",
        "language": "English",
        "prompt": "Open OBS on desktop.",
        "expected_intent": "open_app",
        "requires_confirmation": True,
        "risk_level": "medium",
        "skill_tags": ["[APP]", "[SHOT]"]
    }
]


async def run_evaluation():
    print("=" * 75)
    print("FastAgent 12 Personas & Core Skills Evaluation")
    print("=" * 75)

    channel = MockChannel()
    cal_tool = MockCalendarTool()
    gmail_tool = MockGmailTool()
    orch = CascadeOrchestrator(
        messaging_channel=channel,
        calendar_tool=cal_tool,
        gmail_tool=gmail_tool
    )

    passed_count = 0
    total_latency_ms = 0.0

    for p in PERSONAS:
        pid = p["id"]
        name = p["name"]
        prompt = p["prompt"]
        tags = " ".join(p["skill_tags"])
        user_id = f"user_persona_{pid}"

        t0 = time.perf_counter()

        # Handle offline edge case test for Persona 11
        if p.get("test_offline"):
            with patch.object(presence_manager, "is_online", return_value=False):
                res = await orch.handle_message(user_id=user_id, message_text=prompt)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            total_latency_ms += elapsed_ms

            is_ok = res.status == "offline" and "laptop offline" in res.response_text.lower()
            status_sym = "[PASS]" if is_ok else "[FAIL]"
            if is_ok:
                passed_count += 1
            print(f"{status_sym} #{pid:02d} {name:<30} {tags:<16} Latency: {elapsed_ms:.1f}ms")
            print(f"       Prompt:   '{prompt}'")
            print(f"       Response: '{res.response_text}'\n")
            continue

        async def mock_desktop_send(user_id, command_payload, timeout=10.0):
            intent = command_payload.get("intent", "")
            args = command_payload.get("arguments", {})
            try:
                res_exec = skill_executor.execute_skill(intent, args)
                return {"success": True, "result": res_exec}
            except Exception as ex:
                return {"success": False, "error": str(ex)}

        with patch.object(presence_manager, "is_online", return_value=True):
            with patch.object(presence_manager, "send_command_to_desktop", side_effect=mock_desktop_send):
                res = await orch.handle_message(user_id=user_id, message_text=prompt)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_latency_ms += elapsed_ms

        # Assert intent matches expected (or acceptable compound alternative)
        expected = p["expected_intent"]
        if isinstance(expected, (list, tuple)):
            intent_ok = res.intent in expected
        else:
            intent_ok = res.intent == expected

        conf_ok = True
        if p.get("requires_confirmation"):
            conf_ok = res.status in ("pending_confirmation", "pending")
        else:
            conf_ok = res.status in ("executed", "direct_rule")

        is_ok = intent_ok and conf_ok
        if is_ok:
            passed_count += 1

        status_sym = "[PASS]" if is_ok else "[FAIL]"
        print(f"{status_sym} #{pid:02d} {name:<30} {tags:<16} Latency: {elapsed_ms:.1f}ms")
        print(f"       Prompt:   '{prompt}'")
        print(f"       Intent:   {res.intent} (Risk: {res.risk}, Status: {res.status})")
        print(f"       Response: '{res.response_text[:80]}...'\n")

    avg_latency = total_latency_ms / len(PERSONAS)
    print("=" * 75)
    print(f"Summary: {passed_count}/{len(PERSONAS)} Personas Passed Evaluated")
    print(f"Average End-to-End Orchestrator Decision Latency: {avg_latency:.2f} ms")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_evaluation())
