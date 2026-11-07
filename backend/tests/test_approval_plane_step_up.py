"""Tests for Phase 7: Approval Plane, Step-Up Confirmation, Risk-Tiered TTLs, and Amendment Handling."""
import pytest
import time
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.db.repository import DatabaseRepository
from backend.app.cascade.orchestrator import CascadeOrchestrator
from backend.app.cascade.decision import MockDecisionModel
from backend.app.channels.mock import MockChannel
from backend.app.tools.mock import MockCalendarTool, MockGmailTool
from backend.app.llm.mock import MockLLMProvider
from backend.app.policy.confirmations import RISK_TTL_MAP, is_step_up_confirmed


@pytest.fixture
def test_repo():
    return DatabaseRepository()


@pytest.fixture
def mock_channel():
    return MockChannel()


@pytest.fixture
def orchestrator(test_repo, mock_channel):
    return CascadeOrchestrator(
        decision_model=MockDecisionModel(),
        llm_provider=MockLLMProvider(),
        messaging_channel=mock_channel,
        calendar_tool=MockCalendarTool(),
        gmail_tool=MockGmailTool(),
        db_repo=test_repo
    )


@pytest.mark.asyncio
async def test_risk_tiered_approval_ttls(test_repo):
    """Pending approvals must assign expiration TTLs strictly corresponding to their risk tier."""
    assert RISK_TTL_MAP["low"] == 600
    assert RISK_TTL_MAP["medium"] == 300
    assert RISK_TTL_MAP["high"] == 120
    assert RISK_TTL_MAP["critical"] == 60

    app_low = await test_repo.create_pending_approval(
        user_id="u_low", request_id="r1", query_text="low action",
        intent="open_url", risk="low", confidence=0.9, arguments={}
    )
    assert 590 <= (app_low["expires_at"] - app_low["created_at"]) <= 605

    app_high = await test_repo.create_pending_approval(
        user_id="u_high", request_id="r2", query_text="send confidential email",
        intent="send_email", risk="high", confidence=0.9, arguments={}
    )
    assert 115 <= (app_high["expires_at"] - app_high["created_at"]) <= 125


@pytest.mark.asyncio
async def test_step_up_confirmation_enforcement(orchestrator, test_repo, mock_channel):
    """High risk actions require explicit step-up confirmation; weak affirmations are stopped."""
    user_id = "+15559998888"
    await test_repo.register_user(phone=user_id)

    # 1. Create a high-risk pending approval (e.g. send_email)
    await test_repo.create_pending_approval(
        user_id=user_id,
        request_id="req_high_1",
        query_text="Send email to client",
        intent="send_email",
        risk="high",
        confidence=0.95,
        arguments={"recipient": "client@acme.com", "subject": "Proposal", "body": "Attached"}
    )

    # 2. User sends weak abbreviation "y" -> should be stopped by step-up confirmation
    resp_weak = await orchestrator.handle_message(user_id=user_id, message_text="y")
    assert resp_weak.status == "pending_confirmation"
    assert "HIGH risk level" in resp_weak.response_text
    assert "explicitly with *'confirm'*" in resp_weak.response_text

    # 3. User sends explicit step-up confirmation "confirm" -> executes action
    resp_strong = await orchestrator.handle_message(user_id=user_id, message_text="confirm")
    assert resp_strong.status == "executed"


@pytest.mark.asyncio
async def test_amend_approval_in_place(test_repo):
    """Amending a pending approval updates parameters in place without creating duplicate requests."""
    user_id = "user_amend_1"
    app_rec = await test_repo.create_pending_approval(
        user_id=user_id,
        request_id="req_amend",
        query_text="Schedule meeting Friday 2pm",
        intent="schedule_meeting",
        risk="medium",
        confidence=0.9,
        arguments={"title": "Sync", "start_time": "Friday 2pm"}
    )
    aid = app_rec["id"]

    # Amend start_time to Friday 4pm
    res = await test_repo.amend_approval(
        approval_id=aid,
        caller_user_id=user_id,
        amendments={"start_time": "Friday 4pm", "title": "Updated Sync"}
    )
    assert res["status"] == "amended"
    updated = res["record"]
    assert updated["arguments"]["start_time"] == "Friday 4pm"
    assert updated["arguments"]["title"] == "Updated Sync"

    # Unauthorized caller amendment rejected
    bad_res = await test_repo.amend_approval(
        approval_id=aid,
        caller_user_id="different_attacker",
        amendments={"title": "Hacked"}
    )
    assert "error" in bad_res
    assert "Unauthorized" in bad_res["error"]


@pytest.mark.asyncio
async def test_cleanup_expired_approvals(test_repo):
    """Cleanup routine transitions all pending approvals past their expiration time to expired."""
    user_id = "user_expire_test"
    # Create an approval that expired 10 seconds ago
    app_rec = await test_repo.create_pending_approval(
        user_id=user_id,
        request_id="req_exp",
        query_text="Old action",
        intent="schedule_meeting",
        risk="medium",
        confidence=0.9,
        arguments={},
        expires_in_seconds=-10
    )
    aid = app_rec["id"]

    # Run cleanup
    cleaned_count = await test_repo.cleanup_expired_approvals()
    assert cleaned_count >= 1

    # Verify status is now expired
    fetched = await test_repo.get_approval_by_id(aid)
    assert fetched["status"] == "expired"


@pytest.mark.asyncio
async def test_approvals_fastapi_endpoints():
    """Verifies /api/approvals/cleanup and /{approval_id}/amend HTTP endpoints."""
    from backend.app.db.repository import repository
    user_id = "api_approvals_user"
    app_rec = await repository.create_pending_approval(
        user_id=user_id,
        request_id="req_api_app",
        query_text="Deploy task",
        intent="dispatch_coding_task",
        risk="medium",
        confidence=0.9,
        arguments={"task": "benchmark"}
    )
    aid = app_rec["id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Amend endpoint
        amend_res = await client.post(f"/api/approvals/{aid}/amend", json={
            "amendments": {"task": "production deploy"},
            "caller_user_id": user_id
        })
        assert amend_res.status_code == 200
        assert amend_res.json()["status"] == "amended"

        # 2. Cleanup endpoint
        clean_res = await client.post("/api/approvals/cleanup")
        assert clean_res.status_code == 200
        assert clean_res.json()["status"] == "success"
