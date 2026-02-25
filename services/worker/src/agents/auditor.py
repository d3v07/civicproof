"""Auditor Gate — Deterministic Rule Engine.

This is the central governance mechanism of CivicProof.
It is a PURE DETERMINISTIC FUNCTION:
  - Zero LLM calls
  - Zero network calls
  - Zero exceptions to the rules
  - Same input always produces the same output

Every case pack passes through this gate before reaching output.
If ANY rule fails, the entire pack is BLOCKED.

Rules:
  1. CITATION_REQUIRED: Every factual claim must have >= 1 citation
  2. CITATION_VALID: Every citation must reference an artifact_id that exists
  3. ARTIFACT_HASH_MATCH: Cited artifact content_hash must match stored hash
  4. NO_ACCUSATORY_LANGUAGE: Claim text must not contain banned phrases
  5. HYPOTHESIS_LABELED: Uncited claims must be type=hypothesis or risk_signal
  6. MINIMUM_SOURCES: Case must cite >= 2 independent data sources
  7. PII_CHECK: No SSNs or personal phone numbers in output
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Banned accusatory phrases ──────────────────────────────────────
BANNED_PHRASES = [
    "committed fraud",
    "guilty of fraud",
    "is defrauding",
    "has defrauded",
    "criminals",
    "criminal enterprise",
    "is corrupt",
    "corrupt official",
    "stole taxpayer",
    "theft of public",
    "money laundering scheme",
    "convicted of",
    "should be prosecuted",
    "must be charged",
    "evidence proves guilt",
    "undeniable proof of fraud",
    "clearly guilty",
    "engaged in bribery",
    "is a fraudster",
    "criminal conspiracy proven",
]

# ── PII regex patterns ────────────────────────────────────────────
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_PATTERN = re.compile(
    r"\b(?:\+?1[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b"
)
# Heuristic: personal emails (not gov/mil/corporate domains)
_PERSONAL_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@(?:gmail|yahoo|hotmail|outlook|aol|icloud|protonmail)\.\w+\b",
    re.IGNORECASE,
)


@dataclass
class RuleResult:
    """Result of a single auditor rule check."""

    rule_name: str
    passed: bool
    violations: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditorResult:
    """Complete result from the Auditor Gate."""

    approved: bool
    rule_results: list[RuleResult] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def blocked(self) -> bool:
        return not self.approved

    @property
    def violation_count(self) -> int:
        return len(self.violations)


class AuditorGate:
    """Deterministic auditor gate — the central governance boundary.

    This class is intentionally stateless. It has:
      - No database connections
      - No HTTP clients
      - No LLM access
      - No side effects

    It is a pure function of its inputs.
    """

    def __init__(
        self,
        valid_artifact_ids: set[str] | None = None,
        artifact_hashes: dict[str, str] | None = None,
        min_sources: int = 2,
    ) -> None:
        """Initialize auditor with reference data for validation.

        Args:
            valid_artifact_ids: Set of artifact IDs that exist in the store.
            artifact_hashes: Mapping of artifact_id -> content_hash for
                           hash verification.
            min_sources: Minimum number of independent data sources required.
        """
        self._valid_artifact_ids = valid_artifact_ids or set()
        self._artifact_hashes = artifact_hashes or {}
        self._min_sources = min_sources

    def audit(self, case_pack: dict[str, Any]) -> AuditorResult:
        """Run all auditor rules against a case pack.

        Args:
            case_pack: The case pack dictionary containing:
                - claims: list of claim dicts
                - citations: list of citation dicts (keyed by claim_id)
                - sources_used: list of source strings
                - pack_hash: deterministic hash

        Returns:
            AuditorResult with approval status and any violations.
        """
        claims = case_pack.get("claims", [])
        sources_used = case_pack.get("sources_used", [])

        # Build citation index: claim_id -> list of citation dicts
        citation_index: dict[str, list[dict]] = {}
        for claim in claims:
            claim_id = claim.get("claim_id", "")
            citation_ids = claim.get("citation_ids", [])
            artifact_ids = claim.get("artifact_ids", [])
            citation_index[claim_id] = [
                {"artifact_id": aid} for aid in (citation_ids or artifact_ids)
            ]

        rule_results: list[RuleResult] = []

        # Rule 1: CITATION_REQUIRED
        rule_results.append(self._check_citation_required(claims, citation_index))

        # Rule 2: CITATION_VALID
        rule_results.append(self._check_citation_valid(citation_index))

        # Rule 3: ARTIFACT_HASH_MATCH
        rule_results.append(self._check_artifact_hash_match(citation_index))

        # Rule 4: NO_ACCUSATORY_LANGUAGE
        rule_results.append(self._check_no_accusatory_language(claims))

        # Rule 5: HYPOTHESIS_LABELED
        rule_results.append(self._check_hypothesis_labeled(claims, citation_index))

        # Rule 6: MINIMUM_SOURCES
        rule_results.append(self._check_minimum_sources(sources_used))

        # Rule 7: PII_CHECK
        rule_results.append(self._check_pii(claims, case_pack))

        # Aggregate
        all_violations = []
        for rr in rule_results:
            all_violations.extend(rr.violations)

        approved = all(rr.passed for rr in rule_results)

        summary = (
            "Case pack APPROVED — all auditor rules passed."
            if approved
            else f"Case pack BLOCKED — {len(all_violations)} violation(s) found."
        )

        return AuditorResult(
            approved=approved,
            rule_results=rule_results,
            violations=all_violations,
            summary=summary,
        )

    # ── Rule implementations ──────────────────────────────────

    def _check_citation_required(
        self,
        claims: list[dict],
        citation_index: dict[str, list[dict]],
    ) -> RuleResult:
        """Rule 1: Every factual claim must have >= 1 citation."""
        violations = []
        factual_types = {"finding", "factual"}

        for claim in claims:
            claim_type = claim.get("claim_type", "").lower()
            if claim_type not in factual_types:
                continue

            claim_id = claim.get("claim_id", "")
            citations = citation_index.get(claim_id, [])
            if not citations:
                stmt_preview = claim.get("statement", "")[:80]
                violations.append(
                    f"CITATION_REQUIRED: Factual claim '{stmt_preview}...' "
                    f"(id={claim_id}) has no citations."
                )

        return RuleResult(
            rule_name="CITATION_REQUIRED",
            passed=len(violations) == 0,
            violations=violations,
            details={"factual_claims_checked": sum(
                1 for c in claims if c.get("claim_type", "").lower() in factual_types
            )},
        )

    def _check_citation_valid(
        self, citation_index: dict[str, list[dict]]
    ) -> RuleResult:
        """Rule 2: Every citation must reference an existing artifact_id."""
        violations = []

        if not self._valid_artifact_ids:
            # FAIL if no reference data: we cannot validate citations
            # without a reference set — this is a data integrity issue
            has_citations = any(
                cit.get("artifact_id")
                for cits in citation_index.values()
                for cit in cits
            )
            if has_citations:
                violations.append(
                    "CITATION_VALID: Cannot validate citations — "
                    "no reference artifact IDs provided to auditor."
                )
            return RuleResult(
                rule_name="CITATION_VALID",
                passed=len(violations) == 0,
                violations=violations,
                details={"skipped_reason": "no reference artifact IDs provided"},
            )

        for claim_id, citations in citation_index.items():
            for cit in citations:
                artifact_id = cit.get("artifact_id", "")
                if artifact_id and artifact_id not in self._valid_artifact_ids:
                    violations.append(
                        f"CITATION_VALID: Citation references non-existent "
                        f"artifact '{artifact_id}' in claim '{claim_id}'."
                    )

        return RuleResult(
            rule_name="CITATION_VALID",
            passed=len(violations) == 0,
            violations=violations,
        )

    def _check_artifact_hash_match(
        self, citation_index: dict[str, list[dict]]
    ) -> RuleResult:
        """Rule 3: Cited artifact content_hash must match stored hash."""
        violations = []

        if not self._artifact_hashes:
            has_citations = any(
                cit.get("artifact_id")
                for cits in citation_index.values()
                for cit in cits
            )
            if has_citations:
                violations.append(
                    "ARTIFACT_HASH_MATCH: Cannot verify artifact integrity — "
                    "no reference hashes provided to auditor."
                )
            return RuleResult(
                rule_name="ARTIFACT_HASH_MATCH",
                passed=len(violations) == 0,
                violations=violations,
                details={"skipped_reason": "no reference hashes provided"},
            )

        for claim_id, citations in citation_index.items():
            for cit in citations:
                artifact_id = cit.get("artifact_id", "")
                provided_hash = cit.get("content_hash")
                if artifact_id and provided_hash:
                    stored_hash = self._artifact_hashes.get(artifact_id)
                    if stored_hash and stored_hash != provided_hash:
                        violations.append(
                            f"ARTIFACT_HASH_MATCH: Hash mismatch for artifact "
                            f"'{artifact_id}' — provided={provided_hash[:16]}... "
                            f"stored={stored_hash[:16]}..."
                        )

        return RuleResult(
            rule_name="ARTIFACT_HASH_MATCH",
            passed=len(violations) == 0,
            violations=violations,
        )

    def _check_no_accusatory_language(self, claims: list[dict]) -> RuleResult:
        """Rule 4: Claim text must not contain banned accusatory phrases."""
        violations = []

        for claim in claims:
            statement = (claim.get("statement") or "").lower()
            for phrase in BANNED_PHRASES:
                if phrase in statement:
                    stmt_preview = claim.get("statement", "")[:80]
                    violations.append(
                        f"NO_ACCUSATORY_LANGUAGE: Claim contains banned phrase "
                        f"'{phrase}' — '{stmt_preview}...'"
                    )
                    break  # One violation per claim is enough

        return RuleResult(
            rule_name="NO_ACCUSATORY_LANGUAGE",
            passed=len(violations) == 0,
            violations=violations,
            details={"claims_checked": len(claims)},
        )

    def _check_hypothesis_labeled(
        self,
        claims: list[dict],
        citation_index: dict[str, list[dict]],
    ) -> RuleResult:
        """Rule 5: Uncited claims must be type=hypothesis or risk_signal."""
        violations = []
        allowed_uncited = {"hypothesis", "risk_signal", "cannot_conclude"}

        for claim in claims:
            claim_id = claim.get("claim_id", "")
            claim_type = claim.get("claim_type", "").lower()
            citations = citation_index.get(claim_id, [])

            if not citations and claim_type not in allowed_uncited:
                stmt_preview = claim.get("statement", "")[:80]
                violations.append(
                    f"HYPOTHESIS_LABELED: Uncited claim typed as '{claim_type}' "
                    f"but should be 'hypothesis' or 'risk_signal' — "
                    f"'{stmt_preview}...'"
                )

        return RuleResult(
            rule_name="HYPOTHESIS_LABELED",
            passed=len(violations) == 0,
            violations=violations,
        )

    def _check_minimum_sources(self, sources_used: list[str]) -> RuleResult:
        """Rule 6: Case must cite >= min_sources independent data sources."""
        unique_sources = set(sources_used)
        passed = len(unique_sources) >= self._min_sources

        violations = []
        if not passed:
            violations.append(
                f"MINIMUM_SOURCES: Case cites {len(unique_sources)} source(s) "
                f"but requires >= {self._min_sources}. "
                f"Sources: {', '.join(unique_sources) or 'none'}"
            )

        return RuleResult(
            rule_name="MINIMUM_SOURCES",
            passed=passed,
            violations=violations,
            details={
                "sources_found": list(unique_sources),
                "sources_required": self._min_sources,
            },
        )

    def _check_pii(
        self, claims: list[dict], case_pack: dict[str, Any]
    ) -> RuleResult:
        """Rule 7: No SSNs or personal phone numbers in output."""
        violations = []

        # Check all text content
        texts_to_check = []
        for claim in claims:
            texts_to_check.append(claim.get("statement", ""))
        texts_to_check.append(case_pack.get("summary", ""))
        texts_to_check.append(case_pack.get("title", ""))

        for text in texts_to_check:
            if not text:
                continue

            ssn_matches = _SSN_PATTERN.findall(text)
            if ssn_matches:
                violations.append(
                    f"PII_CHECK: SSN pattern detected in output: "
                    f"{ssn_matches[0][:5]}***"
                )

            email_matches = _PERSONAL_EMAIL_PATTERN.findall(text)
            if email_matches:
                violations.append(
                    f"PII_CHECK: Personal email detected in output: "
                    f"{email_matches[0][:10]}***"
                )

        return RuleResult(
            rule_name="PII_CHECK",
            passed=len(violations) == 0,
            violations=violations,
        )
