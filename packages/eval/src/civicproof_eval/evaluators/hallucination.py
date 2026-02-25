from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_ABSOLUTE_CERTAINTY_PHRASES = [
    re.compile(
        r"\b(definitely|certainly|undoubtedly|it is clear that|proof that|proven)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(committed fraud|is guilty|is a fraud|is fraudulent)\b", re.IGNORECASE),
    re.compile(r"\b(we can confirm|this confirms|this proves)\b", re.IGNORECASE),
]

_REQUIRED_HEDGES = [
    re.compile(
        r"\b(risk signal|hypothesis|suggests|may indicate|potential|alleged|"
        r"suspected|appears to|could indicate)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(cannot conclude|insufficient evidence|further investigation)\b", re.IGNORECASE),
]


class HallucinationEvaluator:
    name = "hallucination"

    def _check_statement(self, statement: str) -> dict[str, Any]:
        violations: list[str] = []
        for pattern in _ABSOLUTE_CERTAINTY_PHRASES:
            match = pattern.search(statement)
            if match:
                violations.append(f"absolute_certainty: '{match.group()}'")

        has_hedge = any(p.search(statement) for p in _REQUIRED_HEDGES)

        return {
            "violations": violations,
            "has_hedge": has_hedge,
        }

    def evaluate(self, record: dict[str, Any]) -> dict[str, Any]:
        claims = record.get("claims", [])
        if not claims:
            return {"passed": True, "score": 1.0, "detail": {"reason": "no_claims"}}

        violations_by_claim: list[dict[str, Any]] = []
        unhedged_factual_claims: list[str] = []

        for claim in claims:
            claim_id = claim.get("claim_id", "unknown")
            statement = claim.get("statement", "")
            claim_type = claim.get("claim_type", "")
            audit_passed = claim.get("audit_passed")

            if audit_passed is False:
                violations_by_claim.append(
                    {"claim_id": claim_id, "reason": "auditor_rejected"}
                )
                continue

            check = self._check_statement(statement)
            if check["violations"]:
                violations_by_claim.append(
                    {
                        "claim_id": claim_id,
                        "reason": "absolute_certainty_language",
                        "violations": check["violations"],
                    }
                )

            if claim_type in ("risk_signal", "hypothesis", "finding") and not check["has_hedge"]:
                unhedged_factual_claims.append(claim_id)

        total = len(claims)
        violation_count = len(violations_by_claim)
        unhedged_count = len(unhedged_factual_claims)
        clean_count = total - violation_count

        score = clean_count / total if total > 0 else 1.0
        passed = violation_count == 0 and unhedged_count == 0

        return {
            "passed": passed,
            "score": score,
            "detail": {
                "total_claims": total,
                "violation_count": violation_count,
                "unhedged_factual_claim_count": unhedged_count,
                "violations": violations_by_claim,
                "unhedged_claim_ids": unhedged_factual_claims,
            },
        }
