"""Test Policy Engine rate limits and confirmation rules."""
import pytest
from backend.app.policy.engine import PolicyEngine


def test_rate_limiter():
    engine = PolicyEngine()
    user_id = "user_rate_test"

    # Send 30 actions within limit
    for _ in range(30):
        assert engine.check_rate_limit(user_id, max_per_minute=30) is True

    # 31st action should be blocked
    assert engine.check_rate_limit(user_id, max_per_minute=30) is False


def test_recipient_allowlist():
    engine = PolicyEngine()
    user_id = "user_allowlist_test"
    engine.set_user_allowlist(user_id, ["@company.com", "partner@external.com"])

    eval1 = engine.evaluate_action(
        user_id=user_id,
        intent="send_email",
        arguments={"recipient": "alex@company.com"},
        confidence=0.95
    )
    assert "External Recipient" not in eval1.suggested_prompt

    eval2 = engine.evaluate_action(
        user_id=user_id,
        intent="send_email",
        arguments={"recipient": "stranger@unknown.com"},
        confidence=0.95
    )
    assert "External Recipient" in eval2.suggested_prompt
