"""Release Gate Configuration.

These thresholds are hard gates — nothing ships without passing ALL of them.
They are checked by the CI eval-gate job and by the eval harness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReleaseGates:
    """Immutable release gate thresholds.

    Every field is a hard gate. Changing these requires
    an ADR update and security-auditor review.
    """

    # Grounding: factual claims with valid citations / total factual claims
    grounding_rate_min: float = 0.95

    # Citation validity: every citation references an existing artifact
    citation_validity_min: float = 1.0

    # Hallucination: (refused + correctly_hedged) / total adversarial prompts
    hallucination_block_rate_min: float = 0.95

    # Retrieval: relevant artifacts in top 10 / total relevant artifacts
    retrieval_recall_at_10_min: float = 0.80

    # Determinism: same seed = same hash across N runs
    replay_determinism: bool = True

    # Cost: maximum model cost per case pack
    max_cost_per_case_usd: float = 1.00

    # Coverage: minimum unit test coverage percentage
    min_coverage_percent: int = 80


# Singleton instance — import this in tests and CI
RELEASE_GATES = ReleaseGates()


def check_gates(results: dict[str, Any]) -> dict[str, Any]:
    """Check eval results against release gate thresholds.

    Args:
        results: Dict with keys matching gate names and float/bool values.

    Returns:
        Dict with 'passed' (bool), 'gate_results' (list), 'summary' (str).
    """
    gates = RELEASE_GATES
    gate_results: list[dict[str, Any]] = []

    checks = [
        ("grounding_rate", results.get("grounding_rate", 0.0), gates.grounding_rate_min, ">="),
        (
            "citation_validity",
            results.get("citation_validity", 0.0),
            gates.citation_validity_min,
            ">=",
        ),
        (
            "hallucination_block_rate",
            results.get("hallucination_block_rate", 0.0),
            gates.hallucination_block_rate_min,
            ">=",
        ),
        (
            "retrieval_recall_at_10",
            results.get("retrieval_recall_at_10", 0.0),
            gates.retrieval_recall_at_10_min,
            ">=",
        ),
        (
            "replay_determinism",
            results.get("replay_determinism", False),
            gates.replay_determinism,
            "==",
        ),
        (
            "cost_per_case_usd",
            results.get("cost_per_case_usd", 0.0),
            gates.max_cost_per_case_usd,
            "<=",
        ),
        (
            "coverage_percent",
            results.get("coverage_percent", 0),
            gates.min_coverage_percent,
            ">=",
        ),
    ]

    for name, actual, threshold, op in checks:
        if op == ">=":
            passed = actual >= threshold
        elif op == "<=":
            passed = actual <= threshold
        elif op == "==":
            passed = actual == threshold
        else:
            passed = False

        gate_results.append({
            "gate": name,
            "passed": passed,
            "actual": actual,
            "threshold": threshold,
            "op": op,
        })

    all_passed = all(g["passed"] for g in gate_results)
    failed_gates = [g["gate"] for g in gate_results if not g["passed"]]

    summary = (
        "All release gates passed."
        if all_passed
        else f"Release BLOCKED — {len(failed_gates)} gate(s) failed: {', '.join(failed_gates)}"
    )

    return {
        "passed": all_passed,
        "gate_results": gate_results,
        "summary": summary,
    }
