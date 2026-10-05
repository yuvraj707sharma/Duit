"""kNN / Semantic memory retriever over explicit user corrections."""
import math
import re
from typing import Dict, List, Optional, Tuple


class TextEmbeddingRetriever:
    """Lightweight character/word n-gram TF-IDF vectorizer and cosine kNN matcher for active learning."""

    def __init__(self, ngram_range: Tuple[int, int] = (2, 4), similarity_threshold: float = 0.65):
        self.ngram_range = ngram_range
        self.similarity_threshold = similarity_threshold
        # Stored records: list of dicts: {"user_id": str, "text": str, "vector": dict, "intent": str}
        self._memory: List[Dict] = []

    def _tokenize_ngrams(self, text: str) -> Dict[str, float]:
        clean = re.sub(r"[^\w\s]", " ", text.lower()).strip()
        words = clean.split()
        ngrams: Dict[str, float] = {}
        
        # Word unigrams and bigrams
        for w in words:
            ngrams[f"w:{w}"] = ngrams.get(f"w:{w}", 0.0) + 1.0
        for i in range(len(words) - 1):
            bi = f"wb:{words[i]}_{words[i+1]}"
            ngrams[bi] = ngrams.get(bi, 0.0) + 1.5

        # Character n-grams for typo & morphological matching (e.g. Hindi/Hinglish inflections)
        for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
            for i in range(len(clean) - n + 1):
                c_ngram = f"c:{clean[i:i+n]}"
                ngrams[c_ngram] = ngrams.get(c_ngram, 0.0) + 0.5

        # L2 Normalization
        norm = math.sqrt(sum(v * v for v in ngrams.values())) or 1.0
        return {k: v / norm for k, v in ngrams.items()}

    def _cosine_similarity(self, vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        # Dot product of normalized vectors
        if len(vec_a) > len(vec_b):
            vec_a, vec_b = vec_b, vec_a
        return sum(val * vec_b.get(k, 0.0) for k, val in vec_a.items())

    def clear(self):
        self._memory.clear()

    def add_correction(self, user_id: str, query_text: str, corrected_intent: str):
        vec = self._tokenize_ngrams(query_text)
        self._memory.append({
            "user_id": user_id,
            "text": query_text,
            "vector": vec,
            "intent": corrected_intent
        })

    def find_nearest_correction(
        self, user_id: str, query_text: str, k: int = 1
    ) -> Optional[Tuple[str, float, str]]:
        """Returns (corrected_intent, similarity_score, matched_text) if similarity >= threshold."""
        query_vec = self._tokenize_ngrams(query_text)
        candidates = [m for m in self._memory if m["user_id"] == user_id or m["user_id"] == "global"]
        if not candidates:
            return None

        best_match = None
        best_sim = -1.0

        for cand in candidates:
            sim = self._cosine_similarity(query_vec, cand["vector"])
            if sim > best_sim:
                best_sim = sim
                best_match = cand

        if best_match and best_sim >= self.similarity_threshold:
            return (best_match["intent"], best_sim, best_match["text"])

        return None


# Global singleton retriever instance
knn_retriever = TextEmbeddingRetriever()
