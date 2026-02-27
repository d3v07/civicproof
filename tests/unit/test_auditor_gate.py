"""Unit tests for the Auditor Gate.

The auditor gate is a PURE DETERMINISTIC function — no mocking needed.
Every test verifies the same-input-same-output invariant.
"""

import pytest
from agents.auditor import AuditorGate

# ── Fixtures ─────────────────────────────────────────────────────


def _valid_pack(
    claims=None, sources=None, summary="Test case summary", title="Test Case"
):
    """Build a minimal valid case pack dict."""
    return {
        "claims": claims or [
            {
                "claim_id": "c1",
                "statement": "Entity received $5M in awards.",
                "claim_type": "finding",
                "confidence": 1.0,
                "citation_ids": ["art-001"],
                "artifact_ids": ["art-001"],
            },
            {
                "claim_id": "c2",
                "statement": "Sole-source pattern detected.",
                "claim_type": "risk_signal",
                "confidence": 0.7,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ],
        "sources_used": sources or ["usaspending", "doj"],
        "summary": summary,
        "title": title,
    }


# ── APPROVAL TESTS ───────────────────────────────────────────────


class TestAuditorApproval:
    """Tests that valid case packs pass the auditor gate."""

    def test_valid_pack_is_approved(self):
        gate = AuditorGate(
            valid_artifact_ids={"art-001"},
            artifact_hashes={"art-001": "abc123"},
            min_sources=2,
        )
        result = gate.audit(_valid_pack())
        assert result.approved is True
        assert result.violation_count == 0

    def test_all_rules_pass_returns_summary(self):
        gate = AuditorGate(
            valid_artifact_ids={"art-001"},
            artifact_hashes={"art-001": "abc123"},
            min_sources=2,
        )
        result = gate.audit(_valid_pack())
        assert "APPROVED" in result.summary

    def test_determinism(self):
        """Same input must always produce same output."""
        gate = AuditorGate(
            valid_artifact_ids={"art-001"},
            artifact_hashes={"art-001": "abc123"},
            min_sources=2,
        )
        pack = _valid_pack()
        result_a = gate.audit(pack)
        result_b = gate.audit(pack)
        assert result_a.approved == result_b.approved
        assert result_a.violations == result_b.violations


# ── CITATION_REQUIRED ─────────────────────────────────────────────


class TestCitationRequired:
    """Rule 1: Every factual claim must have >= 1 citation."""

    def test_factual_claim_without_citation_is_blocked(self):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Entity received awards.",
                "claim_type": "finding",
                "confidence": 1.0,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert result.approved is False
        assert any("CITATION_REQUIRED" in v for v in result.violations)

    def test_hypothesis_without_citation_is_ok(self):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Possible vendor relationship.",
                "claim_type": "hypothesis",
                "confidence": 0.5,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert not any("CITATION_REQUIRED" in v for v in result.violations)


# ── CITATION_VALID ─────────────────────────────────────────────────


class TestCitationValid:
    """Rule 2: Every citation must reference an existing artifact_id."""

    def test_nonexistent_artifact_is_blocked(self):
        gate = AuditorGate(
            valid_artifact_ids={"art-001"},
            min_sources=1,
        )
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Entity received awards.",
                "claim_type": "finding",
                "confidence": 1.0,
                "citation_ids": ["art-999"],
                "artifact_ids": ["art-999"],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert result.approved is False
        assert any("CITATION_VALID" in v for v in result.violations)

    def test_valid_artifact_passes(self):
        gate = AuditorGate(
            valid_artifact_ids={"art-001"},
            min_sources=1,
        )
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Entity received awards.",
                "claim_type": "finding",
                "confidence": 1.0,
                "citation_ids": ["art-001"],
                "artifact_ids": ["art-001"],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert not any("CITATION_VALID" in v for v in result.violations)


# ── NO_ACCUSATORY_LANGUAGE ──────────────────────────────────────


class TestNoAccusatoryLanguage:
    """Rule 4: Claim text must not contain banned phrases."""

    @pytest.mark.parametrize("banned_phrase", [
        "committed fraud",
        "is corrupt",
        "criminals",
        "should be prosecuted",
        "evidence proves guilt",
    ])
    def test_banned_phrase_is_blocked(self, banned_phrase):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": f"The entity {banned_phrase} against the government.",
                "claim_type": "risk_signal",
                "confidence": 0.5,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert any("NO_ACCUSATORY_LANGUAGE" in v for v in result.violations)

    def test_neutral_language_passes(self):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Risk signal: sole-source concentration detected.",
                "claim_type": "risk_signal",
                "confidence": 0.5,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert not any("NO_ACCUSATORY_LANGUAGE" in v for v in result.violations)


# ── HYPOTHESIS_LABELED ──────────────────────────────────────────


class TestHypothesisLabeled:
    """Rule 5: Uncited claims must be hypothesis or risk_signal."""

    def test_uncited_finding_is_blocked(self):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Some factual statement.",
                "claim_type": "finding",
                "confidence": 1.0,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        # Should be blocked by both CITATION_REQUIRED and HYPOTHESIS_LABELED
        assert result.approved is False

    def test_uncited_risk_signal_passes(self):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Possible pattern worth investigating.",
                "claim_type": "risk_signal",
                "confidence": 0.5,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert not any("HYPOTHESIS_LABELED" in v for v in result.violations)


# ── MINIMUM_SOURCES ─────────────────────────────────────────────


class TestMinimumSources:
    """Rule 6: Case must cite >= min_sources independent data sources."""

    def test_single_source_is_blocked(self):
        gate = AuditorGate(min_sources=2)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Test.",
                "claim_type": "risk_signal",
                "confidence": 0.5,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert any("MINIMUM_SOURCES" in v for v in result.violations)

    def test_two_sources_passes(self):
        gate = AuditorGate(min_sources=2)
        pack = _valid_pack(sources=["usaspending", "doj"])
        result = gate.audit(pack)
        assert not any("MINIMUM_SOURCES" in v for v in result.violations)


# ── PII_CHECK ───────────────────────────────────────────────────


class TestPIICheck:
    """Rule 7: No SSNs or personal emails in output."""

    def test_ssn_is_blocked(self):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Person SSN: 123-45-6789",
                "claim_type": "risk_signal",
                "confidence": 0.5,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert any("PII_CHECK" in v for v in result.violations)

    def test_personal_email_is_blocked(self):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Contact: john.doe@gmail.com",
                "claim_type": "risk_signal",
                "confidence": 0.5,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert any("PII_CHECK" in v for v in result.violations)

    def test_gov_email_is_not_flagged(self):
        gate = AuditorGate(min_sources=1)
        pack = _valid_pack(claims=[
            {
                "claim_id": "c1",
                "statement": "Contact: info@agency.gov for details.",
                "claim_type": "risk_signal",
                "confidence": 0.5,
                "citation_ids": [],
                "artifact_ids": [],
            },
        ], sources=["usaspending"])
        result = gate.audit(pack)
        assert not any("PII_CHECK" in v for v in result.violations)
