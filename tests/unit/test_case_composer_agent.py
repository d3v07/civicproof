"""Unit tests for CaseComposerAgent pure logic."""
from __future__ import annotations

import os
import sys

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from src.agents.case_composer import (
    CaseComposerAgent,
    ComposedCasePack,
    ComposedClaim,
    CompositionResult,
)


def _entity_profile(**overrides):
    defaults = {
        "canonical_name": "ACME CORP",
        "entity_type": "vendor",
        "uei": "ABC123DEF456",
    }
    defaults.update(overrides)
    return defaults


def _make_awards(count=3, sole_source=0):
    awards = []
    for i in range(count):
        a = {
            "award_id": f"award-{i}",
            "award_amount": 100000 * (i + 1),
            "awarding_agency": "DOD",
            "start_date": f"2025-0{i+1}-01",
            "extent_competed": "FULL AND OPEN",
        }
        if i < sole_source:
            a["extent_competed"] = "NOT COMPETED"
        awards.append(a)
    return awards


class TestCaseComposerCompose:
    def test_basic_composition(self):
        agent = CaseComposerAgent()
        result = agent.compose(
            case_id="c-1",
            entity_profile=_entity_profile(),
            artifact_ids=["a1", "a2"],
            risk_signals=[],
            awards_data=_make_awards(2),
            sources_used=["usaspending"],
        )

        pack = result.case_pack
        assert pack.case_id == "c-1"
        assert "ACME CORP" in pack.title
        assert len(pack.claims) >= 2  # entity_registered + award_total
        assert pack.pack_hash != ""
        assert pack.evidence_summary["total_artifacts"] == 2

    def test_risk_signals_added_as_claims(self):
        agent = CaseComposerAgent()
        signals = [
            {"signal_type": "sole_source", "score": 0.7, "description": "High sole-source", "severity": "medium"},
        ]
        result = agent.compose(
            case_id="c-1",
            entity_profile=_entity_profile(),
            artifact_ids=["a1"],
            risk_signals=signals,
            awards_data=[],
            sources_used=["usaspending"],
        )

        risk_claims = [c for c in result.case_pack.claims if c.claim_type == "risk_signal"]
        assert len(risk_claims) == 1
        assert "High sole-source" in risk_claims[0].statement

    def test_sole_source_claim_generated(self):
        agent = CaseComposerAgent()
        result = agent.compose(
            case_id="c-1",
            entity_profile=_entity_profile(),
            artifact_ids=["a1", "a2"],
            risk_signals=[],
            awards_data=_make_awards(3, sole_source=2),
            sources_used=["usaspending"],
        )

        statements = [c.statement for c in result.case_pack.claims]
        assert any("sole-source" in s for s in statements)

    def test_empty_awards_no_award_claims(self):
        agent = CaseComposerAgent()
        result = agent.compose(
            case_id="c-1",
            entity_profile=_entity_profile(),
            artifact_ids=["a1"],
            risk_signals=[],
            awards_data=[],
            sources_used=["usaspending"],
        )

        # Only entity claims, no award claims
        claims = result.case_pack.claims
        assert all(c.claim_type == "finding" for c in claims)

    def test_uei_claim_generated(self):
        agent = CaseComposerAgent()
        result = agent.compose(
            case_id="c-1",
            entity_profile=_entity_profile(uei="TEST123UEI456"),
            artifact_ids=["a1"],
            risk_signals=[],
            awards_data=[],
            sources_used=["usaspending"],
        )

        statements = [c.statement for c in result.case_pack.claims]
        assert any("TEST123UEI456" in s for s in statements)

    def test_no_artifacts_no_entity_claims(self):
        agent = CaseComposerAgent()
        result = agent.compose(
            case_id="c-1",
            entity_profile=_entity_profile(),
            artifact_ids=[],
            risk_signals=[],
            awards_data=[],
            sources_used=[],
        )

        assert len(result.case_pack.claims) == 0

    def test_summary_includes_disclaimer(self):
        agent = CaseComposerAgent()
        result = agent.compose(
            case_id="c-1",
            entity_profile=_entity_profile(),
            artifact_ids=["a1"],
            risk_signals=[],
            awards_data=[],
            sources_used=["usaspending"],
        )

        assert "does not constitute an accusation" in result.case_pack.summary

    def test_summary_mentions_risk_count(self):
        agent = CaseComposerAgent()
        signals = [
            {"signal_type": "x", "score": 0.5, "description": "d", "severity": "high"},
            {"signal_type": "y", "score": 0.3, "description": "e", "severity": "low"},
        ]
        result = agent.compose(
            case_id="c-1",
            entity_profile=_entity_profile(),
            artifact_ids=["a1"],
            risk_signals=signals,
            awards_data=[],
            sources_used=["usaspending"],
        )

        assert "2 risk signal" in result.case_pack.summary
        assert "1 high-severity" in result.case_pack.summary


class TestComposedCasePackHash:
    def test_hash_deterministic(self):
        pack = ComposedCasePack(case_id="c-1", title="T", summary="S")
        h1 = pack.compute_hash()
        h2 = pack.compute_hash()
        assert h1 == h2
        assert len(h1) > 10

    def test_different_claims_different_hash(self):
        p1 = ComposedCasePack(case_id="c-1", title="T", summary="S")
        p1.claims.append(ComposedClaim(
            claim_id="c1", statement="Test", claim_type="finding",
            confidence=1.0, citation_ids=["a1"],
        ))
        h1 = p1.compute_hash()

        p2 = ComposedCasePack(case_id="c-1", title="T", summary="S")
        p2.claims.append(ComposedClaim(
            claim_id="c1", statement="Different", claim_type="finding",
            confidence=1.0, citation_ids=["a1"],
        ))
        h2 = p2.compute_hash()

        assert h1 != h2

    def test_claim_order_independent(self):
        p1 = ComposedCasePack(case_id="c-1", title="T", summary="S")
        p1.claims = [
            ComposedClaim(claim_id="a", statement="A", claim_type="f", confidence=1.0),
            ComposedClaim(claim_id="b", statement="B", claim_type="f", confidence=1.0),
        ]

        p2 = ComposedCasePack(case_id="c-1", title="T", summary="S")
        p2.claims = [
            ComposedClaim(claim_id="b", statement="B", claim_type="f", confidence=1.0),
            ComposedClaim(claim_id="a", statement="A", claim_type="f", confidence=1.0),
        ]

        assert p1.compute_hash() == p2.compute_hash()


class TestDeterministicClaimId:
    def test_same_inputs_same_id(self):
        id1 = CaseComposerAgent._deterministic_claim_id("c-1", "key", "stmt")
        id2 = CaseComposerAgent._deterministic_claim_id("c-1", "key", "stmt")
        assert id1 == id2

    def test_different_inputs_different_id(self):
        id1 = CaseComposerAgent._deterministic_claim_id("c-1", "key", "stmt1")
        id2 = CaseComposerAgent._deterministic_claim_id("c-1", "key", "stmt2")
        assert id1 != id2

    def test_id_length(self):
        cid = CaseComposerAgent._deterministic_claim_id("c-1", "key", "stmt")
        assert len(cid) == 32


class TestBuildTimeline:
    def test_builds_sorted_timeline(self):
        agent = CaseComposerAgent()
        awards = [
            {"start_date": "2025-03-01", "award_id": "a3", "award_amount": 300},
            {"start_date": "2025-01-01", "award_id": "a1", "award_amount": 100},
            {"start_date": "2025-02-01", "award_id": "a2", "award_amount": 200},
        ]
        timeline = agent._build_timeline(awards)
        assert len(timeline) == 3
        assert timeline[0]["date"] == "2025-01-01"
        assert timeline[2]["date"] == "2025-03-01"

    def test_skips_awards_without_date(self):
        agent = CaseComposerAgent()
        awards = [{"award_id": "a1", "award_amount": 100}]
        timeline = agent._build_timeline(awards)
        assert len(timeline) == 0

    def test_empty_awards(self):
        agent = CaseComposerAgent()
        assert agent._build_timeline([]) == []
