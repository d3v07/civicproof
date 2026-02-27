"""Determinism Evaluator.

Verifies that the CivicProof pipeline produces identical results
when run on the same inputs. This is a core invariant:
  same seed + same artifacts → same pack_hash

This evaluator runs the case composer N times and checks that
all resulting hashes are identical.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DeterminismEvaluator:
    """Evaluates replay determinism of case pack generation.

    Input record format:
        {
            "case_id": str,
            "pack_hashes": [str, str, str],  # hashes from N runs
            "claims_per_run": [[claim, ...], [claim, ...], ...],
        }
    """

    name = "determinism"

    def __init__(self, min_runs: int = 3) -> None:
        self._min_runs = min_runs

    def evaluate(self, record: dict[str, Any]) -> dict[str, Any]:
        pack_hashes = record.get("pack_hashes", [])

        if len(pack_hashes) < self._min_runs:
            return {
                "passed": False,
                "score": 0.0,
                "detail": {
                    "reason": "insufficient_runs",
                    "runs_provided": len(pack_hashes),
                    "runs_required": self._min_runs,
                },
            }

        unique_hashes = set(pack_hashes)
        is_deterministic = len(unique_hashes) == 1

        # Also check claim-level determinism if provided
        claims_per_run = record.get("claims_per_run", [])
        claim_count_variance = 0
        if claims_per_run and len(claims_per_run) >= 2:
            counts = [len(run) for run in claims_per_run]
            claim_count_variance = max(counts) - min(counts)

        score = 1.0 if is_deterministic else (1.0 / len(unique_hashes))

        return {
            "passed": is_deterministic and claim_count_variance == 0,
            "score": score,
            "detail": {
                "total_runs": len(pack_hashes),
                "unique_hashes": len(unique_hashes),
                "hashes": pack_hashes,
                "claim_count_variance": claim_count_variance,
                "is_hash_deterministic": is_deterministic,
            },
        }
