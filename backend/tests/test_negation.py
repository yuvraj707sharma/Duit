"""Test handling of negation in user commands."""
import pytest
from backend.app.cascade.decision import MockDecisionModel


@pytest.mark.asyncio
async def test_negation_intent_classification():
    model = MockDecisionModel()
    
    # User explicitly negates cancel and requests reschedule
    msg = "Don't cancel my 3pm sync, but move my 5pm with Rahul to tomorrow at 4pm"
    decision = await model.decide(msg)
    
    assert decision.intent == "reschedule_meeting"
    assert decision.risk in ("medium", "high")
    assert decision.confidence >= 0.90


@pytest.mark.asyncio
async def test_hinglish_negation(orchestrator):
    # Hindi/Hinglish negation
    msg = "Kal ki meeting cancel mat karo, bas aage badhao 5 baje"
    res = await orchestrator.handle_message("user_hinglish_1", msg)
    
    assert res.intent == "reschedule_meeting"
    assert res.status == "pending_confirmation"
