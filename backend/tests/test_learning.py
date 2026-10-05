"""Test continuous learning loop and active threshold tuning."""
import pytest
from backend.app.learning.log import learning_logger
from backend.app.learning.thresholds import threshold_calibrator
from backend.app.learning.retrieval import correction_retriever


def test_learning_loop_explicit_actions_only():
    user_id = "user_learn_101"
    
    # Silence is not logged
    learning_logger.log_correction(user_id, "Query text", "schedule_meeting", "silence")
    assert len(learning_logger.get_records_for_user(user_id)) == 0

    # Explicit approval is logged
    learning_logger.log_correction(user_id, "Schedule sync with Rahul", "schedule_meeting", "approve")
    assert len(learning_logger.get_records_for_user(user_id)) == 1

    # Threshold calibrates after consistent approvals
    for i in range(12):
        learning_logger.log_correction(user_id, f"Schedule meeting {i}", "schedule_meeting", "approve")

    thresh = threshold_calibrator.calculate_threshold(user_id, "schedule_meeting")
    # Lowers threshold to auto-approve high confidence future actions
    assert thresh <= 0.85


def test_few_shot_retrieval():
    user_id = "user_fewshot_202"
    learning_logger.log_correction(user_id, "Book flights to Mumbai", "book_something", "approve")
    learning_logger.log_correction(user_id, "Send monthly update to team", "send_email", "approve")

    similars = correction_retriever.find_similar_corrections(user_id, "flights to Mumbai next week")
    assert len(similars) >= 1
    assert similars[0].predicted_intent == "book_something"
