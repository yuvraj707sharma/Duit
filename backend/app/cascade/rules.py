"""Stage 1: Hard Rules in Code (Emergency halts, static blocklists, syntax allowlists)."""
import re
from typing import Optional, Dict, Any
from pydantic import BaseModel


class RuleResult(BaseModel):
    matched: bool
    direct_response: Optional[str] = None
    action_override: Optional[str] = None
    reason: Optional[str] = None


class HardRulesEngine:
    """Executes deterministic sub-millisecond static rules before any model is invoked."""

    def evaluate(self, text: str) -> RuleResult:
        cleaned = text.strip().lower()

        # 1. Emergency Kill / Stop / Pause
        if cleaned in ("stop", "pause", "cancel all", "emergency stop", "halt"):
            return RuleResult(
                matched=True,
                direct_response="🛑 All automated pending actions have been halted. Type 'resume' or send a new request.",
                action_override="halt_all",
                reason="emergency_halt"
            )

        # 2. System Help / Capabilities
        if cleaned in ("help", "?", "what can you do", "commands"):
            return RuleResult(
                matched=True,
                direct_response=(
                    "🤖 *FastAgent Capabilities:*\n"
                    "• *Calendar:* 'Schedule sync with Rahul tomorrow 4pm', 'Check my calendar'\n"
                    "• *Email:* 'Reply yes to Amit's email', 'Summarize unread emails'\n"
                    "• *Hindi/Hinglish:* 'Kal subah 10 baje meeting rakh do'\n"
                    "• *Safety:* Side effects require your confirmation."
                ),
                reason="help_menu"
            )

        # 3. Simple Greetings (avoid LLM/Laya invocation)
        if cleaned in ("hi", "hello", "hey", "namaste", "hola"):
            return RuleResult(
                matched=True,
                direct_response="Hello! How can I assist with your scheduling or emails today?",
                reason="greeting"
            )

        # 3.5. Google Connect Command
        if cleaned in ("connect google", "connect to google", "link google", "link to google", "google connect", "link my google", "connect my google"):
            return RuleResult(
                matched=True,
                direct_response="🔗 *Link your Google Account:*\nPlease tap the authentication link sent to you on WhatsApp or type *'connect google'* to authorize your Google Calendar and Gmail.",
                reason="google_connect"
            )

        # 3.6. Shed Remote Coding Agent Plane
        if cleaned in ("shed", "shed status", "remote status", "coding status", "agent status"):
            return RuleResult(
                matched=True,
                direct_response=(
                    "🖥️ *Shed Remote Coding Task Plane (e:\\Inovvate\\shed):*\n"
                    "• *State:* Connected & Ready\n"
                    "• *Harnesses:* Claude Code, Codex, Gemini, OpenCode\n"
                    "• *Capabilities:* Start coding sessions, inspect live terminals, and run tasks remotely from your phone.\n"
                    "• *Usage:* Text *'code: <prompt>'* or check *'skills'* to trigger desktop tasks."
                ),
                reason="shed_status"
            )

        # 3.7. Skills Library Catalog
        if cleaned in ("skills", "skills library", "list skills", "show skills", "skills list"):
            return RuleResult(
                matched=True,
                direct_response=(
                    "📦 *ZORO Skills Library (e:\\Inovvate\\skills):*\n"
                    "• 📄 *PDF Generator:* 'Generate PDF report of my meetings'\n"
                    "• 🔍 *Web Researcher:* 'Research latest updates on AI agents'\n"
                    "• ⏰ *Recurring Briefing:* 'Brief me every morning at 9am'\n"
                    "• 💻 *Code Auditor:* 'Audit code for security issues'\n"
                    "• 📊 *SQL Analyst:* 'Query database stats'"
                ),
                reason="skills_library"
            )

        # 4. Dangerous System / Shell Injection Blocklist
        injection_patterns = [
            r"rm\s+-rf",
            r"drop\s+table",
            r"select\s+\*\s+from",
            r"format\s+c:",
            r"/bin/sh",
            r"__import__"
        ]
        for pattern in injection_patterns:
            if re.search(pattern, cleaned):
                return RuleResult(
                    matched=True,
                    direct_response="⚠️ Invalid request: command contains blocked system patterns.",
                    reason="security_blocklist"
                )

        # No rule match -> proceed to Stage 2 (Laya Decision Layer)
        return RuleResult(matched=False)


hard_rules_engine = HardRulesEngine()
