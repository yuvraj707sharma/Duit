"""Skill Security and Privileged Prompt Isolation Engine for DUIT.

Enforces:
- Prohibits user-created skills from defining arbitrary server-side webhooks.
- Scans system prompts for prompt injection, policy bypass, or privileged shell execution attempts.
- Enforces strict SSRF protection on all authorized webhook URLs.
"""
import re
from typing import Optional, Tuple
from backend.app.security.ssrf import validate_safe_url


# Patterns that attempt to hijack control flow, bypass confirmation safety, or execute privileged commands
PROHIBITED_PROMPT_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(the\s+)?(system|policy|developer)\s+instructions?",
    r"bypass\s+(safety|security|policy|confirmations?|approvals?)",
    r"disable\s+(safety|security|policy|confirmations?|approvals?)",
    r"skip\s+(safety|security|policy|confirmations?|approvals?)",
    r"do\s+not\s+ask\s+(for\s+)?confirmations?",
    r"execute\s+(arbitrary\s+)?(shell|command|bash|powershell|cmd)",
    r"run\s+(shell|command|bash|powershell|cmd)",
    r"format\s+[a-z]:",
    r"rm\s+-rf",
    r"del\s+/f\s+/s",
    r"extract\s+(passwords?|credentials?|tokens?|keys?)",
    r"dump\s+(secrets?|database|lsass|shadow)",
    r"grant\s+(root|admin|superuser)\s+access",
]

_COMPILED_PROMPT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PROHIBITED_PROMPT_PATTERNS]


def validate_skill_definition(
    name: str,
    system_prompt: str,
    user_id: str,
    webhook_url: Optional[str] = None,
    is_admin: bool = False,
    resolve_dns: bool = True
) -> Tuple[bool, str]:
    """Validates that a skill does not violate platform boundaries, security policies, or privileged prompts."""
    if not name or not name.strip():
        return False, "Skill name cannot be empty"

    if not system_prompt or not system_prompt.strip():
        return False, "System prompt cannot be empty"

    # 1. Prohibit arbitrary server-side webhooks on user-created skills
    clean_user = (user_id or "").strip().upper()
    is_global_or_admin = is_admin or clean_user == "GLOBAL"

    if webhook_url and webhook_url.strip():
        if not is_global_or_admin:
            return False, "User-created skills are prohibited from defining arbitrary server-side webhooks. Webhook integrations require administrator authorization."

        # Even for admins, validate webhook against SSRF
        is_safe, error_msg = validate_safe_url(webhook_url.strip(), require_https=False, resolve_dns=resolve_dns)
        if not is_safe:
            return False, f"Prohibited webhook URL: {error_msg}"

    # 2. Scan system prompt for privileged escalation or safety bypass patterns
    for pattern in _COMPILED_PROMPT_PATTERNS:
        match = pattern.search(system_prompt)
        if match:
            matched_text = match.group(0)
            return False, f"System prompt contains prohibited privileged directives or policy bypass: '{matched_text}'"

    return True, ""
