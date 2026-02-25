from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RetrievalEvaluator:
    name = "retrieval"

    def __init__(self, k: int = 5) -> None:
        self._k = k

    def _recall_at_k(self, retrieved: list[str], relevant: list[str], k: int) -> float:
        if not relevant:
            return 1.0
        top_k = set(retrieved[:k])
        relevant_set = set(relevant)
        hits = len(top_k & relevant_set)
        return hits / len(relevant_set)

    def _precision_at_k(self, retrieved: list[str], relevant: list[str], k: int) -> float:
        if not retrieved:
            return 0.0
        top_k = retrieved[:k]
        relevant_set = set(relevant)
        hits = sum(1 for r in top_k if r in relevant_set)
        return hits / k

    def _average_precision(self, retrieved: list[str], relevant: list[str]) -> float:
        if not relevant:
            return 1.0
        relevant_set = set(relevant)
        hits = 0
        precision_sum = 0.0
        for i, item in enumerate(retrieved, start=1):
            if item in relevant_set:
                hits += 1
                precision_sum += hits / i
        if hits == 0:
            return 0.0
        return precision_sum / len(relevant_set)

    def evaluate(self, record: dict[str, Any]) -> dict[str, Any]:
        retrieved_artifact_ids: list[str] = record.get("retrieved_artifact_ids", [])
        relevant_artifact_ids: list[str] = record.get("relevant_artifact_ids", [])

        if not relevant_artifact_ids:
            return {
                "passed": True,
                "score": 1.0,
                "detail": {"reason": "no_relevant_set_defined"},
            }

        recall = self._recall_at_k(retrieved_artifact_ids, relevant_artifact_ids, self._k)
        precision = self._precision_at_k(retrieved_artifact_ids, relevant_artifact_ids, self._k)
        avg_precision = self._average_precision(retrieved_artifact_ids, relevant_artifact_ids)

        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        passed = recall >= 0.8

        return {
            "passed": passed,
            "score": recall,
            "detail": {
                f"recall@{self._k}": round(recall, 4),
                f"precision@{self._k}": round(precision, 4),
                "average_precision": round(avg_precision, 4),
                "f1": round(f1, 4),
                "retrieved_count": len(retrieved_artifact_ids),
                "relevant_count": len(relevant_artifact_ids),
            },
        }
