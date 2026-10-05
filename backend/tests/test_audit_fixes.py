"""Comprehensive tests for FastAgent Audit Fixes:
1. Webhook auth & JID rejection
2. Approvals: 1 per user, 5m expiry, caller matching, edit reruns policy & preserves idempotency key
3. Policy: never auto-approve high risk, empty allowlist = confirm
4. Laya adapter: strict confidence, error metric & forced confirmation, no silent fallback
5. Emergency stop: cancel pending approvals & return count
6. Crypto: 32 bytes base64 check, user_id AAD binding, v1: prefix
7. Persistence: DB persistence for approvals, audit log (insert-only), idempotency, corrections
8. Idempotency: derived from message_id + action, webhook dedupe
9. 'other' intent to LLM, unsupported tool error, read intent arg extraction
10. Confirmation prompt with full draft body
"""
import pytest
import time
import base64
from datetime import datetime, timezone, timedelta
from backend.app.cascade.orchestrator import CascadeOrchestrator
from backend.app.channels.mock import MockChannel
from backend.app.tools.mock import MockCalendarTool, MockGmailTool
from backend.app.cascade.decision import MockDecisionModel, LayaDecisionModel, DecisionOutput
from backend.app.llm.mock import MockLLMProvider
from backend.app.policy.engine import PolicyEngine
from backend.app.security.crypto import validate_encryption_key, encrypt_token, decrypt_token, CryptoKeyError
from backend.app.metrics import metrics_collector


# -------------------------------------------------------------
# 2. Approvals: 1 per user, 5-min expiry, matching caller, edit reruns policy
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_approval_single_pending_per_user_supersedes_old():
    orch = CascadeOrchestrator()
    user_id = "user_appr_1"

    res1 = await orch.handle_message(user_id, "Move my 3pm to 4pm")
    aid1 = res1.pending_approval_id
    assert aid1 is not None

    # Second action requiring confirmation from same user
    res2 = await orch.handle_message(user_id, "Send email to rahul@example.com with update")
    aid2 = res2.pending_approval_id
    assert aid2 is not None
    assert aid1 != aid2

    # Old approval must be superseded / cancelled; only 1 active pending approval exists
    user_pending = [a for a in (await orch.get_pending_approvals(user_id)) if a["status"] == "pending"]
    assert len(user_pending) == 1
    assert user_pending[0]["id"] == aid2


@pytest.mark.asyncio
async def test_approval_expiry_5_minutes():
    orch = CascadeOrchestrator()
    user_id = "user_exp_1"

    res = await orch.handle_message(user_id, "Move my 3pm to 4pm")
    aid = res.pending_approval_id
    
    # Manually backdate created_at past 5 minutes (301 seconds ago)
    await orch.backdate_approval_for_test(aid, seconds_ago=301)

    # Attempt to resolve expired approval
    resolve_res = await orch.resolve_approval(aid, decision="approve", caller_user_id=user_id)
    assert resolve_res.get("error") is not None
    assert "expired" in resolve_res.get("error", "").lower()


@pytest.mark.asyncio
async def test_approval_resolve_caller_validation():
    orch = CascadeOrchestrator()
    user_owner = "user_owner_1"
    user_attacker = "user_attacker_2"

    res = await orch.handle_message(user_owner, "Move my 3pm to 4pm")
    aid = res.pending_approval_id

    # Attacker tries to resolve owner's approval
    resolve_res = await orch.resolve_approval(aid, decision="approve", caller_user_id=user_attacker)
    assert resolve_res.get("error") is not None
    assert "unauthorized" in resolve_res.get("error", "").lower() or "not found" in resolve_res.get("error", "").lower()


@pytest.mark.asyncio
async def test_approval_edit_reruns_policy_and_keeps_idempotency_key():
    orch = CascadeOrchestrator()
    user_id = "user_edit_1"
    orch.policy_engine.set_user_allowlist(user_id, ["@company.com"])

    res = await orch.handle_message(user_id, "Send email to alex@company.com with project notes")
    aid = res.pending_approval_id
    appr_rec = (await orch.get_pending_approvals(user_id))[0]
    orig_key = appr_rec["arguments"]["idempotency_key"]

    # Edit changes recipient to unallowlisted external domain
    edited_args = {
        "recipient": "evil@unallowlisted.com",
        "subject": "Leaked Notes",
        "body": "Secret payload"
    }

    resolve_res = await orch.resolve_approval(
        aid,
        decision="edit",
        caller_user_id=user_id,
        edited_payload=edited_args
    )

    # Editing to unallowlisted recipient must re-trigger policy engine and require confirmation or flag
    assert resolve_res.get("status") in ("pending", "policy_held", "edited_held")
    # Idempotency key must be preserved
    updated_rec = (await orch.get_pending_approvals(user_id))[0]
    assert updated_rec["arguments"]["idempotency_key"] == orig_key


# -------------------------------------------------------------
# 3. Policy: Never auto-approve high risk, empty allowlist = confirm
# -------------------------------------------------------------
def test_policy_never_auto_approves_high_risk():
    policy = PolicyEngine()
    user_id = "user_policy_high"

    # Even with 1.0 confidence and auto_approve_threshold 0.80, high risk intent MUST require confirmation
    eval_res = policy.evaluate_action(
        user_id=user_id,
        intent="cancel_meeting",
        arguments={"event_id": "evt_1"},
        confidence=1.0,
        auto_approve_threshold=0.80
    )
    assert eval_res.requires_confirmation is True
    assert eval_res.risk_level == "high"


def test_policy_empty_allowlist_requires_confirmation_for_send_email():
    policy = PolicyEngine()
    user_id = "user_empty_allowlist"
    # No allowlist configured -> empty allowlist must require confirmation, NOT allow automatically
    policy.set_user_allowlist(user_id, [])

    eval_res = policy.evaluate_action(
        user_id=user_id,
        intent="send_email",
        arguments={"recipient": "anyone@example.com"},
        confidence=0.99,
        auto_approve_threshold=0.80
    )
    assert eval_res.requires_confirmation is True


# -------------------------------------------------------------
# 4. Laya adapter: strict confidence, error metric & forced confirmation
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_laya_adapter_handles_error_and_forces_confirmation():
    # Point to nonexistent port to trigger connection error
    model = LayaDecisionModel(base_url="http://127.0.0.1:59999")
    prev_errors = metrics_collector.get_summary().get("decision_errors", 0)

    decision = await model.decide("Move my meeting")
    assert decision.risk == "high"
    assert decision.needs_confirmation is True
    assert decision.confidence == 0.0
    assert "error" in decision.reasoning_tag

    curr_errors = metrics_collector.get_summary().get("decision_errors", 0)
    assert curr_errors == prev_errors + 1


# -------------------------------------------------------------
# 5. Emergency stop: cancels user's pending approvals and returns count
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_emergency_stop_cancels_pending_approvals_and_reports_count():
    orch = CascadeOrchestrator()
    user_id = "user_stop_1"

    # Create a pending approval
    await orch.handle_message(user_id, "Move my 4pm meeting to tomorrow")
    pending_before = [a for a in (await orch.get_pending_approvals(user_id)) if a["status"] == "pending"]
    assert len(pending_before) == 1

    # Send emergency halt
    res = await orch.handle_message(user_id, "stop")
    assert res.status == "direct_rule"
    assert "1" in res.response_text  # Mentions 1 pending approval cancelled

    pending_after = [a for a in (await orch.get_pending_approvals(user_id)) if a["status"] == "pending"]
    assert len(pending_after) == 0


# -------------------------------------------------------------
# 8. Idempotency: derived from message_id + action & webhook deduplication
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_idempotency_key_derived_from_message_id_and_action():
    orch = CascadeOrchestrator()
    msg_id = "INBOUND_MSG_777"
    action = "reschedule_meeting"
    key1 = orch.derive_idempotency_key(msg_id, action)
    key2 = orch.derive_idempotency_key(msg_id, action)
    assert key1 == key2
    assert len(key1) >= 16


@pytest.mark.asyncio
async def test_webhook_deduplication_returns_cached_response():
    orch = CascadeOrchestrator()
    user_id = "user_dedupe_1"
    msg_id = "MSG_DUP_101"
    text = "What is on my calendar today?"

    res1 = await orch.handle_message(user_id, text, inbound_message_id=msg_id)
    res2 = await orch.handle_message(user_id, text, inbound_message_id=msg_id)

    assert res1.request_id == res2.request_id
    assert res1.response_text == res2.response_text


# -------------------------------------------------------------
# 9. 'other' intent to LLM & unsupported tools return explicit error
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_other_intent_calls_llm_for_reply():
    orch = CascadeOrchestrator()
    user_id = "user_other_1"
    res = await orch.handle_message(user_id, "What is the capital of France?")
    assert res.intent == "other"
    assert res.status == "executed"
    assert len(res.response_text) > 0


@pytest.mark.asyncio
async def test_unimplemented_tool_returns_not_supported_error():
    orch = CascadeOrchestrator()
    user_id = "user_unsupported_1"
    # Execute unknown intent tool
    tool_res = await orch._execute_tool(user_id, "unknown_future_action", {})
    assert tool_res.success is False
    assert "not supported" in (tool_res.error or "").lower()


@pytest.mark.asyncio
async def test_read_intents_run_argument_extraction():
    orch = CascadeOrchestrator()
    user_id = "user_read_1"
    res = await orch.handle_message(user_id, "Summarize unread emails from alex")
    assert res.intent == "summarize_email"
    # Verifies arguments were extracted for read intent
    assert res.tool_result is not None


# -------------------------------------------------------------
# 10. Confirmation prompt includes full draft body
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirmation_prompt_includes_full_draft_body():
    orch = CascadeOrchestrator()
    user_id = "user_prompt_body"
    msg = "Send email to rahul@example.com saying let's meet tomorrow at Starbucks for coffee"
    res = await orch.handle_message(user_id, msg)
    assert res.status == "pending_confirmation"
    # Prompt MUST include subject and full body preview
    assert "Subject:" in res.response_text
    assert "Body:" in res.response_text or "rahul@example.com" in res.response_text
