"""Few-Shot Similarity Retrieval of past user corrections."""
import math
from typing import List, Dict, Any, Optional
from backend.app.learning.log import learning_logger, CorrectionRecord


def _simple_text_vector(text: str) -> Dict[str, float]:
    """Lightweight character/word n-gram vector for fast similarity in absence of full embedding model."""
    words = text.lower().split()
    counts: Dict[str, float] = {}
    for w in words:
        counts[w] = counts.get(w, 0.0) + 1.0
    # Normalize length
    norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
    return {k: v / norm for k, v in counts.items()}


def _cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    common = set(vec1.keys()) & set(vec2.keys())
    return sum(vec1[k] * vec2[k] for k in common)


class CorrectionRetriever:
    """Retrieves top-k similar past corrections for a user to provide dynamic few-shot context."""

    def find_similar_corrections(
        self,
        user_id: str,
        query: str,
        top_k: int = 3
    ) -> List[CorrectionRecord]:
        records = learning_logger.get_records_for_user(user_id)
        if not records:
            return []

        query_vec = _simple_text_vector(query)
        scored: List[tuple[float, CorrectionRecord]] = []

        for rec in records:
            rec_vec = _simple_text_vector(rec.query_text)
            score = _cosine_similarity(query_vec, rec_vec)
            if score > 0.2:  # Relevancy gate
                scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]


correction_retriever = CorrectionRetriever()
