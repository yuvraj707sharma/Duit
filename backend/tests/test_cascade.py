"""Test end-to-end 4-stage cascade pipeline."""
import pytest


@pytest.mark.asyncio
async def test_stage_1_emergency_stop(orchestrator):
    res = await orchestrator.handle_message("user_test", "stop")
    assert res.status == "direct_rule"
    assert "halted" in res.response_text.lower()
    assert res.stage_latencies_ms.get("stage_1_rules", 0) >= 0


@pytest.mark.asyncio
async def test_stage_2_read_query_no_llm_call(orchestrator):
    res = await orchestrator.handle_message("user_test", "What is on my calendar today?")
    assert res.intent == "check_calendar"
    assert res.status == "executed"
    # Stage 3 LLM extraction is skipped for read queries
    assert res.stage_latencies_ms.get("stage_3_llm_extraction", 0) >= 0


@pytest.mark.asyncio
async def test_full_confirmation_flow(orchestrator, mock_channel):
    user_id = "user_flow_101"
    
    # 1. User asks to move meeting
    res = await orchestrator.handle_message(user_id, "Move my 4pm meeting with Rahul to tomorrow")
    assert res.status == "pending_confirmation"
    assert res.pending_approval_id is not None
    assert len(mock_channel.confirmation_prompts) == 1

    # 2. User confirms via WhatsApp
    confirm_res = await orchestrator.handle_message(user_id, "YES")
    assert confirm_res.status == "executed"
    assert "confirmed" in confirm_res.response_text.lower()
