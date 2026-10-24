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
                direct_response="All automated pending actions have been halted. Type 'resume' or send a new request.",
                action_override="halt_all",
                reason="emergency_halt"
            )

        # 2. System Help / Capabilities
        if cleaned in ("help", "?", "what can you do", "commands"):
            return RuleResult(
                matched=True,
                direct_response=(
                    "*FastAgent Capabilities:*\n"
                    "- Calendar: 'Schedule sync with Rahul tomorrow 4pm', 'Check my calendar'\n"
                    "- Email: 'Reply yes to Amit's email', 'Summarize unread emails'\n"
                    "- Coding: 'Shed status', 'Start coding <task>'\n"
                    "- Shopping: 'Add boat headphones to cart'\n"
                    "- Hindi/Hinglish: 'Kal subah 10 baje meeting rakh do'\n"
                    "- Safety: Side effects require your confirmation."
                ),
                reason="help_menu"
            )

        # 3.7. Skills Library Catalog
        if cleaned in ("skills", "skills library", "list skills", "show skills", "skills list"):
            return RuleResult(
                matched=True,
                direct_response=(
                    "*ZORO Skills Library (e:\\Inovvate\\skills):*\n"
                    "• *PDF Generator:* 'Generate PDF report of my meetings'\n"
                    "• *Web Researcher:* 'Research latest updates on AI agents'\n"
                    "• *Recurring Briefing:* 'Brief me every morning at 9am'\n"
                    "• *Code Auditor:* 'Audit code for security issues'\n"
                    "• *SQL Analyst:* 'Query database stats'"
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
                    direct_response="Invalid request: command contains blocked system patterns.",
                    reason="security_blocklist"
                )

        # No rule match -> proceed to Stage 2 (Laya Decision Layer)
        return RuleResult(matched=False)


hard_rules_engine = HardRulesEngine()
