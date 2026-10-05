"""Test strict user scoping and tenant isolation."""
import pytest


@pytest.mark.asyncio
async def test_tenant_isolation(orchestrator):
    user_a = "user_alpha_111"
    user_b = "user_beta_222"

    # User A initiates an action requiring confirmation
    res_a = await orchestrator.handle_message(user_a, "Cancel my 4pm meeting")
    assert res_a.pending_approval_id is not None

    # User B should have 0 pending approvals
    user_b_approvals = [
        rec for rec in orchestrator.pending_approvals.values()
        if rec["user_id"] == user_b and rec["status"] == "pending"
    ]
    assert len(user_b_approvals) == 0

    # User A should have 1 pending approval
    user_a_approvals = [
        rec for rec in orchestrator.pending_approvals.values()
        if rec["user_id"] == user_a and rec["status"] == "pending"
    ]
    assert len(user_a_approvals) == 1

    # User B replying "YES" will NOT approve User A's pending action
    res_b = await orchestrator.handle_message(user_b, "YES")
    # Should not resolve User A's action
    assert orchestrator.pending_approvals[res_a.pending_approval_id]["status"] == "pending"
