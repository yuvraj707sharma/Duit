"""Calculates per-action auto-approve confidence thresholds from historical explicit approvals."""
from typing import Dict, List, Optional
from backend.app.learning.log import learning_logger


class ThresholdCalibrator:
    """Dynamically tunes auto-approval confidence thresholds per user and per action."""

    def __init__(self, min_samples: int = 5):
        self.min_samples = min_samples

    def calculate_threshold(self, user_id: str, action: str) -> Optional[float]:
        records = [
            r for r in learning_logger.get_records_for_user(user_id)
            if r.predicted_intent == action
        ]
        # Never auto-approve on fresh accounts without explicit historical sample baseline
        if len(records) < self.min_samples:
            return None

        approvals = sum(1 for r in records if r.user_action == "approve")
        rejections = sum(1 for r in records if r.user_action in ("reject", "edit"))

        total = approvals + rejections
        if total < self.min_samples:
            return None

        approval_rate = approvals / total
        # If user consistently approves (>95% rate over 10+ samples), gently enable auto-approve threshold at 0.90
        if approval_rate >= 0.95 and total >= 10:
            return 0.85
        elif approval_rate >= 0.90:
            return 0.92
        else:
            # If user has rejected or edited frequently, raise threshold high so confirmation is required
            return 0.99


threshold_calibrator = ThresholdCalibrator()
