"""Evaluation Suite: Testing FastAgent across all 70 Global Scenarios.

Regions:
  - India: Scenarios 1 - 18
  - United States: Scenarios 19 - 36
  - China: Scenarios 37 - 53
  - Japan: Scenarios 54 - 70

Skills Covered:
  [CAL]   Calendar (schedule, reschedule, cancel, check)
  [MAIL]  Gmail (draft, send with confirmation, summarize)
  [VOICE] Voice STT (Hinglish, Hindi, English, Mandarin, Japanese)
  [APP]   Open & verify desktop apps (universal resolver)
  [FILE]  Find, read, and create files
  [SHOT]  Screenshot proof
  [BRIEF] Scheduled morning briefing synthesis
  [RUN]   Shed coding task dispatch & status
"""
import asyncio
import time
import os
import re
from typing import Dict, Any, List
from unittest.mock import patch

from backend.app.cascade.orchestrator import CascadeOrchestrator
from backend.app.desktop.skills import skill_executor
from backend.app.desktop.presence import presence_manager
from backend.app.channels.mock import MockChannel
from backend.app.tools.mock import MockCalendarTool, MockGmailTool


SCENARIOS_DATA = [
    # --- INDIA (1 - 18) ---
    {
        "id": 1, "region": "India", "persona": "Kirana shop owner",
        "prompt": "Aaj ka udhaar sheet laptop se bhejo.",
        "skills": ["[VOICE]", "[FILE]"], "expected_intent": ("search_files", "open_app"),
        "requires_confirmation": False
    },
    {
        "id": 2, "region": "India", "persona": "Chartered accountant",
        "prompt": "Put GST filing deadline on the calendar for Friday 5 PM and draft email to clients.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": ("schedule_meeting", "send_email"),
        "requires_confirmation": True
    },
    {
        "id": 3, "region": "India", "persona": "Wedding planner",
        "prompt": "Schedule meeting with caterer and decorator for tomorrow 3 PM and email each a brief.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": ("schedule_meeting", "send_email"),
        "requires_confirmation": True
    },
    {
        "id": 4, "region": "India", "persona": "Cloud kitchen owner",
        "prompt": "Open the order dashboard on desktop and screenshot today's orders.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": ("open_app", "open_url"),
        "requires_confirmation": True
    },
    {
        "id": 5, "region": "India", "persona": "Coaching class owner",
        "prompt": "Send email to parents regarding fee reminder for this month.",
        "skills": ["[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 6, "region": "India", "persona": "Real estate agent",
        "prompt": "Book site visit on the calendar for Saturday 11 AM with client.",
        "skills": ["[CAL]", "[FILE]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 7, "region": "India", "persona": "Freelance video editor",
        "prompt": "Open Premiere on desktop to check if render finished.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 8, "region": "India", "persona": "IT employee WFH",
        "prompt": "Open Jira on desktop computer.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 9, "region": "India", "persona": "Farmer cooperative secretary",
        "prompt": "Send email to mandi buyer regarding wheat shipment dispatch.",
        "skills": ["[VOICE]", "[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 10, "region": "India", "persona": "District court lawyer",
        "prompt": "Schedule hearing date on calendar for tomorrow 10 AM.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 11, "region": "India", "persona": "Boutique owner",
        "prompt": "Send email to customer with winter collection details.",
        "skills": ["[FILE]", "[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 12, "region": "India", "persona": "Travel agent",
        "prompt": "Schedule itinerary review meeting on calendar for Friday 4 PM.",
        "skills": ["[MAIL]", "[CAL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 13, "region": "India", "persona": "Auto garage owner",
        "prompt": "Schedule service slot on calendar for car inspection tomorrow 2 PM.",
        "skills": ["[FILE]", "[CAL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 14, "region": "India", "persona": "NGO coordinator",
        "prompt": "Schedule volunteer sync on calendar for Sunday 10 AM.",
        "skills": ["[CAL]", "[BRIEF]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 15, "region": "India", "persona": "Bengaluru startup founder",
        "prompt": "Summarize my unread emails and briefing for today.",
        "skills": ["[BRIEF]", "[VOICE]", "[CAL]"], "expected_intent": "summarize_email",
        "requires_confirmation": False
    },
    {
        "id": 16, "region": "India", "persona": "Retired bank officer",
        "prompt": "Find my electricity bill email and summarize latest mails.",
        "skills": ["[VOICE]", "[MAIL]", "[CAL]"], "expected_intent": "summarize_email",
        "requires_confirmation": False
    },
    {
        "id": 17, "region": "India", "persona": "Hinglish content creator",
        "prompt": "Open OBS on desktop.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 18, "region": "India", "persona": "Hotel front desk manager",
        "prompt": "Open booking sheet on desktop.",
        "skills": ["[MAIL]", "[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },

    # --- UNITED STATES (19 - 36) ---
    {
        "id": 19, "region": "United States", "persona": "Real estate agent",
        "prompt": "Schedule open house on calendar for Sunday 1 PM to 4 PM.",
        "skills": ["[CAL]", "[MAIL]", "[FILE]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 20, "region": "United States", "persona": "Plumber/contractor",
        "prompt": "Reschedule today's site appointment to tomorrow 9 AM.",
        "skills": ["[CAL]", "[FILE]"], "expected_intent": "reschedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 21, "region": "United States", "persona": "Solo lawyer",
        "prompt": "Check calendar for free slots tomorrow afternoon.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "check_calendar",
        "requires_confirmation": False
    },
    {
        "id": 22, "region": "United States", "persona": "Gig driver",
        "prompt": "Find files matching mileage on my computer.",
        "skills": ["[FILE]"], "expected_intent": "search_files",
        "requires_confirmation": False
    },
    {
        "id": 23, "region": "United States", "persona": "Nurse",
        "prompt": "Schedule shift swap with Sarah on calendar for Thursday 7 AM.",
        "skills": ["[MAIL]", "[CAL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 24, "region": "United States", "persona": "Remote software engineer",
        "prompt": "Check Shed status on my workstation.",
        "skills": ["[RUN]", "[SHOT]"], "expected_intent": "shed_status",
        "requires_confirmation": False
    },
    {
        "id": 25, "region": "United States", "persona": "Product manager",
        "prompt": "Summarize unread emails and morning briefing.",
        "skills": ["[BRIEF]"], "expected_intent": "summarize_email",
        "requires_confirmation": False
    },
    {
        "id": 26, "region": "United States", "persona": "Etsy seller",
        "prompt": "Open shipping app on desktop.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 27, "region": "United States", "persona": "College student",
        "prompt": "Create note Midterm_Review with content study chapters 4 through 7.",
        "skills": ["[FILE]", "[CAL]"], "expected_intent": "create_note",
        "requires_confirmation": False
    },
    {
        "id": 28, "region": "United States", "persona": "Parent of three",
        "prompt": "Schedule soccer practice on calendar for Tuesday 4 PM.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 29, "region": "United States", "persona": "Retiree",
        "prompt": "Check my unread emails for tax documents.",
        "skills": ["[MAIL]", "[CAL]"], "expected_intent": "summarize_email",
        "requires_confirmation": False
    },
    {
        "id": 30, "region": "United States", "persona": "Podcast producer",
        "prompt": "Open Audacity on desktop.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 31, "region": "United States", "persona": "Freelance designer",
        "prompt": "Send email to client with project deliverables update.",
        "skills": ["[FILE]", "[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 32, "region": "United States", "persona": "Restaurant GM",
        "prompt": "Send email to food vendor confirming weekly meat delivery.",
        "skills": ["[FILE]", "[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 33, "region": "United States", "persona": "Financial advisor assistant",
        "prompt": "Schedule quarterly portfolio review on calendar for next Monday 10 AM.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 34, "region": "United States", "persona": "Teacher",
        "prompt": "Send email to parents regarding quarterly progress report.",
        "skills": ["[FILE]", "[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 35, "region": "United States", "persona": "Journalist",
        "prompt": "Schedule interview on calendar for Thursday 2 PM.",
        "skills": ["[CAL]", "[APP]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 36, "region": "United States", "persona": "User with limited mobility",
        "prompt": "Open notepad on desktop.",
        "skills": ["[VOICE]", "[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },

    # --- CHINA (37 - 53) ---
    {
        "id": 37, "region": "China", "persona": "Shenzhen cross-border seller",
        "prompt": "Open Amazon seller central on desktop.",
        "skills": ["[MAIL]", "[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 38, "region": "China", "persona": "Export factory manager",
        "prompt": "Schedule Zoom call on calendar for tomorrow 8 PM with buyer.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 39, "region": "China", "persona": "Live-stream seller",
        "prompt": "Open OBS on desktop to verify stream.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 40, "region": "China", "persona": "Mini-program developer",
        "prompt": "Check Shed status for build harnesses.",
        "skills": ["[RUN]"], "expected_intent": "shed_status",
        "requires_confirmation": False
    },
    {
        "id": 41, "region": "China", "persona": "Hangzhou founder",
        "prompt": "Summarize my unread emails and briefings.",
        "skills": ["[BRIEF]"], "expected_intent": "summarize_email",
        "requires_confirmation": False
    },
    {
        "id": 42, "region": "China", "persona": "Taobao shop owner",
        "prompt": "Search files for orders report on desktop.",
        "skills": ["[FILE]"], "expected_intent": "search_files",
        "requires_confirmation": False
    },
    {
        "id": 43, "region": "China", "persona": "Chinese student abroad",
        "prompt": "Send email to professor regarding assignment submission.",
        "skills": ["[VOICE]", "[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 44, "region": "China", "persona": "Inbound tourism agent",
        "prompt": "Schedule Shanghai tour on calendar for Friday 9 AM.",
        "skills": ["[MAIL]", "[CAL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 45, "region": "China", "persona": "Accountant",
        "prompt": "Search files for tax invoice fapiao on desktop.",
        "skills": ["[FILE]", "[MAIL]"], "expected_intent": "search_files",
        "requires_confirmation": False
    },
    {
        "id": 46, "region": "China", "persona": "School administrator",
        "prompt": "Schedule parent-teacher conference on calendar for Monday 10 AM.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 47, "region": "China", "persona": "Elderly user",
        "prompt": "Schedule family call on calendar for tomorrow 6 PM.",
        "skills": ["[VOICE]", "[CAL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 48, "region": "China", "persona": "Chengdu restaurant owner",
        "prompt": "Open POS billing app on desktop.",
        "skills": ["[MAIL]", "[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 49, "region": "China", "persona": "Logistics coordinator",
        "prompt": "Open tracking dashboard on desktop.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 50, "region": "China", "persona": "Designer",
        "prompt": "Open Blender on desktop to check render.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 51, "region": "China", "persona": "Foreign traveler in Shanghai",
        "prompt": "Check calendar for my scheduled itinerary today.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "check_calendar",
        "requires_confirmation": False
    },
    {
        "id": 52, "region": "China", "persona": "Hardware engineer",
        "prompt": "Open AutoCAD on desktop.",
        "skills": ["[APP]", "[FILE]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 53, "region": "China", "persona": "Freelance translator",
        "prompt": "Schedule translation review on calendar for Wednesday 3 PM.",
        "skills": ["[CAL]", "[FILE]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },

    # --- JAPAN (54 - 70) ---
    {
        "id": 54, "region": "Japan", "persona": "Office worker",
        "prompt": "Reply to email with formal confirmation.",
        "skills": ["[MAIL]"], "expected_intent": "reply_email",
        "requires_confirmation": True
    },
    {
        "id": 55, "region": "Japan", "persona": "Izakaya owner",
        "prompt": "Schedule reservation on calendar for Friday 7 PM table 4.",
        "skills": ["[MAIL]", "[CAL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 56, "region": "Japan", "persona": "Elderly user",
        "prompt": "Schedule family gathering on calendar for Sunday 12 PM.",
        "skills": ["[VOICE]", "[CAL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 57, "region": "Japan", "persona": "Convenience store owner",
        "prompt": "Search files for shift schedule on desktop.",
        "skills": ["[FILE]"], "expected_intent": "search_files",
        "requires_confirmation": False
    },
    {
        "id": 58, "region": "Japan", "persona": "Game developer",
        "prompt": "Check Shed status on workstation.",
        "skills": ["[RUN]", "[SHOT]"], "expected_intent": "shed_status",
        "requires_confirmation": False
    },
    {
        "id": 59, "region": "Japan", "persona": "Illustrator",
        "prompt": "Open Clip Studio on desktop.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 60, "region": "Japan", "persona": "Ryokan manager",
        "prompt": "Send email to guests with check-in instructions.",
        "skills": ["[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 61, "region": "Japan", "persona": "University researcher",
        "prompt": "Schedule lab meeting on calendar for Thursday 10 AM.",
        "skills": ["[CAL]", "[APP]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 62, "region": "Japan", "persona": "Tax accountant",
        "prompt": "Summarize unread emails for tax filing updates.",
        "skills": ["[CAL]", "[BRIEF]"], "expected_intent": "summarize_email",
        "requires_confirmation": False
    },
    {
        "id": 63, "region": "Japan", "persona": "Tour guide",
        "prompt": "Schedule Tokyo tour on calendar for tomorrow 9 AM.",
        "skills": ["[MAIL]", "[CAL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 64, "region": "Japan", "persona": "Telework employee",
        "prompt": "Open Slack on desktop.",
        "skills": ["[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 65, "region": "Japan", "persona": "Real estate agent",
        "prompt": "Schedule property viewing on calendar for Saturday 2 PM.",
        "skills": ["[CAL]", "[FILE]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 66, "region": "Japan", "persona": "Small manufacturer",
        "prompt": "Send email to client with component quote.",
        "skills": ["[FILE]", "[MAIL]"], "expected_intent": "send_email",
        "requires_confirmation": True
    },
    {
        "id": 67, "region": "Japan", "persona": "Care office coordinator",
        "prompt": "Schedule staff review on calendar for Wednesday 1 PM.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "schedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 68, "region": "Japan", "persona": "Kyoto cafe owner",
        "prompt": "Open sales dashboard on desktop.",
        "skills": ["[MAIL]", "[APP]", "[SHOT]"], "expected_intent": "open_app",
        "requires_confirmation": True
    },
    {
        "id": 69, "region": "Japan", "persona": "Commuter on a train",
        "prompt": "Reschedule meeting to 4 PM tomorrow.",
        "skills": ["[CAL]", "[MAIL]"], "expected_intent": "reschedule_meeting",
        "requires_confirmation": True
    },
    {
        "id": 70, "region": "Japan", "persona": "Freelance writer",
        "prompt": "Open Word on desktop.",
        "skills": ["[APP]", "[CAL]"], "expected_intent": "open_app",
        "requires_confirmation": True
    }
]


async def run_70_scenarios_evaluation():
    print("=" * 80)
    print("FastAgent 70 Global Scenarios Comprehensive Evaluation Suite")
    print("=" * 80)

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
    region_stats = {"India": [0, 0], "United States": [0, 0], "China": [0, 0], "Japan": [0, 0]}

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
            for s in SCENARIOS_DATA:
                sid = s["id"]
                region = s["region"]
                persona = s["persona"]
                prompt = s["prompt"]
                expected = s["expected_intent"]
                tags = " ".join(s["skills"])
                user_id = f"user_scen_{sid}"

                region_stats[region][1] += 1
                t0 = time.perf_counter()
                res = await orch.handle_message(user_id=user_id, message_text=prompt)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                total_latency_ms += elapsed_ms

                # Check intent
                if isinstance(expected, (list, tuple)):
                    intent_ok = res.intent in expected
                else:
                    intent_ok = res.intent == expected

                # Check confirmation safety
                if s.get("requires_confirmation"):
                    conf_ok = res.status in ("pending_confirmation", "pending")
                else:
                    conf_ok = res.status in ("executed", "direct_rule")

                is_ok = intent_ok and conf_ok
                if is_ok:
                    passed_count += 1
                    region_stats[region][0] += 1

                sym = "[PASS]" if is_ok else "[FAIL]"
                print(f"{sym} #{sid:02d} [{region:<13}] {persona:<28} {tags:<16} Latency: {elapsed_ms:.1f}ms", flush=True)
                print(f"       Prompt: '{prompt}'", flush=True)
                print(f"       Intent: {res.intent} (Risk: {res.risk}, Status: {res.status})\n", flush=True)

    avg_latency = total_latency_ms / len(SCENARIOS_DATA)
    print("=" * 80)
    print(f"Overall Evaluation Summary: {passed_count}/{len(SCENARIOS_DATA)} Passed ({(passed_count/len(SCENARIOS_DATA))*100:.1f}%)")
    print(f"Average Orchestrator Decision Latency: {avg_latency:.2f} ms")
    print("-" * 80)
    print("Regional Breakdown:")
    for reg, (p, tot) in region_stats.items():
        pct = (p / tot) * 100 if tot else 0
        print(f"  - {reg:<15}: {p}/{tot} passed ({pct:.1f}%)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_70_scenarios_evaluation())
