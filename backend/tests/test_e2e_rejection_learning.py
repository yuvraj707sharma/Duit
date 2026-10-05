"""End-to-end test: Negation prompt misclassified by stubbed router generates confirmation showing original text, and rejecting it logs a correction."""
import pytest
from backend.app.cascade.orchestrator import CascadeOrchestrator
from backend.app.cascade.decision import DecisionModel, DecisionOutput
from backend.app.learning.log import learning_logger
from backend.app.channels.mock import MockChannel


class StubbedMisclassifyingRouter(DecisionModel):
    """Stubbed router that incorrectly predicts cancel_meeting on negation sentence."""
    async def decide(self, message: str, context=None) -> DecisionOutput:
        return DecisionOutput(
            intent="cancel_meeting",
            risk="high",
            needs_confirmation=True,
            confidence=0.90,
            detected_language="hi-Latn",
            model_used="stubbed-misclassifying-router",
            reasoning_tag="stub_misclassification"
        )


@pytest.mark.asyncio
async def test_e2e_negation_confirmation_and_rejection_learning():
    mock_channel = MockChannel()
    router = StubbedMisclassifyingRouter()
    orch = CascadeOrchestrator(
        decision_model=router,
        messaging_channel=mock_channel
    )

    user_id = "user_e2e_negation_test"
    input_text = "Kal ki meeting cancel mat karo bas shift kar do"

    # 1. User sends message -> Router returns cancel_meeting at 0.90
    res = await orch.handle_message(
        user_id=user_id,
        message_text=input_text
    )

    # 2. Assert user gets a pending confirmation gating the action
    assert res.status == "pending_confirmation"
    assert res.pending_approval_id is not None

    # 3. Assert the confirmation prompt includes the user's original query text
    assert len(mock_channel.confirmation_prompts) >= 1
    confirmation_msg = mock_channel.confirmation_prompts[-1]
    assert input_text in confirmation_msg["text"]

    # 4. User rejects the cancellation ("no" / "reject")
    prior_record_count = len(learning_logger.get_records_for_user(user_id))
    reject_res = await orch.handle_message(
        user_id=user_id,
        message_text="no"
    )

    assert reject_res.status == "rejected"

    # 5. Assert rejecting it logs a correction in the continuous learning dataset
    user_records = learning_logger.get_records_for_user(user_id)
    assert len(user_records) == prior_record_count + 1
    last_record = user_records[-1]
    assert last_record.query_text == input_text
    assert last_record.predicted_intent == "cancel_meeting"
    assert last_record.user_action == "reject"
