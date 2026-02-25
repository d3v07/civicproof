from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GroundingEvaluator:
    name = "grounding"

    def evaluate(self, record: dict[str, Any]) -> dict[str, Any]:
        claims = record.get("claims", [])
        citations = record.get("citations", [])
        artifact_ids = record.get("artifact_ids", [])

        if not claims:
            return {"passed": True, "score": 1.0, "detail": {"reason": "no_claims_to_check"}}

        cited_artifact_ids = {c.get("artifact_id") for c in citations}
        valid_artifact_ids = set(artifact_ids)

        claim_ids_with_citations = {c.get("claim_id") for c in citations if c.get("claim_id")}
        all_claim_ids = {c.get("claim_id") for c in claims}
        uncited_claims = all_claim_ids - claim_ids_with_citations

        invalid_citations = cited_artifact_ids - valid_artifact_ids if valid_artifact_ids else set()

        cannot_conclude_claims = [
            c for c in claims if c.get("claim_type") == "cannot_conclude"
        ]

        grounded_count = len(all_claim_ids) - len(uncited_claims)
        total_count = len(all_claim_ids)
        score = grounded_count / total_count if total_count > 0 else 1.0

        passed = (
            len(uncited_claims) == 0
            and len(invalid_citations) == 0
        )

        return {
            "passed": passed,
            "score": score,
            "detail": {
                "total_claims": total_count,
                "grounded_claims": grounded_count,
                "uncited_claim_ids": list(uncited_claims),
                "invalid_citation_artifact_ids": list(invalid_citations),
                "cannot_conclude_count": len(cannot_conclude_claims),
            },
        }
