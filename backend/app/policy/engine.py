"""Code-level Policy Engine enforcing allowlists, third-party trigger gates, and rate limits."""
import time
from typing import Dict, Any, List, Optional
from backend.app.policy.confirmations import PolicyEvaluation, INTENT_RISK_MAP, build_confirmation_prompt


class PolicyEngine:
    def __init__(self):
        # In-memory rate limiter: user_id -> list of timestamps
        self._user_action_timestamps: Dict[str, List[float]] = {}
        # Recipient allowlists: user_id -> list of domains/emails
        self._allowlists: Dict[str, List[str]] = {}

    def set_user_allowlist(self, user_id: str, allowlist: List[str]):
        self._allowlists[user_id] = [a.lower().strip() for a in allowlist]

    def _is_recipient_allowlisted(self, user_id: str, recipient: str) -> bool:
        if not recipient:
            return False
        rec = recipient.lower().strip()
        user_list = self._allowlists.get(user_id, [])
        # Fix 3: Empty allowlist requires confirmation, not automatic allow
        if not user_list:
            return False
        for allowed in user_list:
            if rec == allowed or (allowed.startswith("@") and rec.endswith(allowed)):
                return True
        return False

    def check_rate_limit(self, user_id: str, max_per_minute: int = 30) -> bool:
        now = time.time()
        timestamps = self._user_action_timestamps.get(user_id, [])
        # Filter timestamps within last 60 seconds
        valid = [t for t in timestamps if now - t < 60]
        if len(valid) >= max_per_minute:
            return False
        valid.append(now)
        self._user_action_timestamps[user_id] = valid
        return True

    def evaluate_action(
        self,
        user_id: str,
        intent: str,
        arguments: Dict[str, Any],
        confidence: float,
        source_is_third_party: bool = False,
        trust_taint: bool = False,
        auto_approve_threshold: Optional[float] = None
    ) -> PolicyEvaluation:
        # 1. Rate limit check
        if not self.check_rate_limit(user_id):
            return PolicyEvaluation(
                allowed=False,
                requires_confirmation=False,
                risk_level="high",
                reasoning="User rate limit exceeded (maximum 30 actions/min)."
            )

        # 2. Rule: Inbound 3rd-party trigger or trust-tainted content ALWAYS requires primary user confirmation
        if trust_taint or source_is_third_party:
            prompt = build_confirmation_prompt(intent, arguments)
            return PolicyEvaluation(
                allowed=True,
                requires_confirmation=True,
                risk_level="high",
                reasoning="Inbound action or text contains trust-tainted third-party content and requires explicit user confirmation.",
                suggested_prompt=f"⚠️ Inbound Request (Untrusted / Tainted):\n{prompt}"
            )

        # 3. Base risk and confirmation lookup
        base_risk, base_requires_conf = INTENT_RISK_MAP.get(intent, ("low", False))

        # 4. Check recipient allowlist for email actions
        if intent in ("send_email", "reply_email"):
            recipient = arguments.get("recipient", "")
            if not self._is_recipient_allowlisted(user_id, recipient):
                prompt = build_confirmation_prompt(intent, arguments)
                return PolicyEvaluation(
                    allowed=True,
                    requires_confirmation=True,
                    risk_level="high",
                    reasoning=f"Recipient '{recipient}' is not on your verified allowlist.",
                    suggested_prompt=f"⚠️ External Recipient (Unverified):\n{prompt}"
                )

        # 5. Low confidence override
        if confidence < 0.75:
            prompt = build_confirmation_prompt(intent, arguments)
            return PolicyEvaluation(
                allowed=True,
                requires_confirmation=True,
                risk_level="medium",
                reasoning=f"Low decision confidence ({confidence:.2f} < 0.75).",
                suggested_prompt=prompt
            )

        # 6. Active learning auto-approve threshold check
        # Fix 3: Never auto-approve intents with risk HIGH (e.g. cancel_meeting, send_email, book_something)
        if base_risk != "high" and auto_approve_threshold is not None and confidence >= auto_approve_threshold:
            base_requires_conf = False

        prompt = build_confirmation_prompt(intent, arguments) if base_requires_conf else ""
        return PolicyEvaluation(
            allowed=True,
            requires_confirmation=base_requires_conf,
            risk_level=base_risk,
            reasoning="Policy evaluated according to code rules.",
            suggested_prompt=prompt
        )


policy_engine = PolicyEngine()
