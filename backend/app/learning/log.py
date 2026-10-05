"""Append-only Learning Dataset and Correction Logger."""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from datetime import datetime, timezone


class CorrectionRecord(BaseModel):
    user_id: str
    query_text: str
    predicted_intent: str
    user_action: str  # approve, edit, reject
    corrected_intent: Optional[str] = None
    corrected_payload: Optional[Dict[str, Any]] = None
    timestamp: datetime = datetime.now(timezone.utc)


class LearningLogger:
    def __init__(self):
        # In-memory append-only log for fast retrieval and evaluation
        self._records: List[CorrectionRecord] = []

    def log_correction(
        self,
        user_id: str,
        query_text: str,
        predicted_intent: str,
        user_action: str,
        corrected_intent: Optional[str] = None,
        corrected_payload: Optional[Dict[str, Any]] = None
    ):
        """Logs explicit user approvals, edits, or rejections. Never logs silence."""
        if user_action not in ("approve", "edit", "reject"):
            return

        record = CorrectionRecord(
            user_id=user_id,
            query_text=query_text,
            predicted_intent=predicted_intent,
            user_action=user_action,
            corrected_intent=corrected_intent or (predicted_intent if user_action == "approve" else None),
            corrected_payload=corrected_payload
        )
        self._records.append(record)

        # Index in kNN retriever for semantic memory lookup
        final_intent = record.corrected_intent or (predicted_intent if user_action == "approve" else None)
        if final_intent:
            from backend.app.learning.knn import knn_retriever
            knn_retriever.add_correction(user_id, query_text, final_intent)

    def get_records_for_user(self, user_id: str) -> List[CorrectionRecord]:
        return [r for r in self._records if r.user_id == user_id]

    def get_all_records(self) -> List[CorrectionRecord]:
        return list(self._records)


learning_logger = LearningLogger()
