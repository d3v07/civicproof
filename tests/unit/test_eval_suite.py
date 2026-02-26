"""Unit tests for eval components.

Tests for: grounding evaluator, hallucination evaluator,
determinism evaluator, synthetic fraud generator, and
release gate threshold checking.
"""

from __future__ import annotations

from civicproof_eval.config import RELEASE_GATES, check_gates
from civicproof_eval.evaluators.determinism import DeterminismEvaluator
from civicproof_eval.evaluators.grounding import GroundingEvaluator
from civicproof_eval.evaluators.hallucination import HallucinationEvaluator
from civicproof_eval.generators.synthetic_fraud import (
    SyntheticFraudGenerator,
    SyntheticFraudScenario,
)
from civicproof_eval.harness import EvalHarness, EvalReport

# ── Grounding Evaluator ──────────────────────────────────────────


class TestGroundingEvaluator:
    def test_fully_grounded_passes(self):
        ev = GroundingEvaluator()
        record = {
            "claims": [
                {"claim_id": "c1", "claim_type": "finding"},
                {"claim_id": "c2", "claim_type": "finding"},
            ],
            "citations": [
                {"claim_id": "c1", "artifact_id": "art-001"},
                {"claim_id": "c2", "artifact_id": "art-002"},
            ],
            "artifact_ids": ["art-001", "art-002"],
        }
        result = ev.evaluate(record)
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_uncited_claim_fails(self):
        ev = GroundingEvaluator()
        record = {
            "claims": [
                {"claim_id": "c1", "claim_type": "finding"},
                {"claim_id": "c2", "claim_type": "finding"},
            ],
            "citations": [
                {"claim_id": "c1", "artifact_id": "art-001"},
            ],
            "artifact_ids": ["art-001"],
        }
        result = ev.evaluate(record)
        assert result["passed"] is False
        assert result["score"] == 0.5

    def test_invalid_citation_artifact_fails(self):
        ev = GroundingEvaluator()
        record = {
            "claims": [{"claim_id": "c1", "claim_type": "finding"}],
            "citations": [{"claim_id": "c1", "artifact_id": "art-FAKE"}],
            "artifact_ids": ["art-001"],
        }
        result = ev.evaluate(record)
        assert result["passed"] is False

    def test_empty_claims_passes(self):
        ev = GroundingEvaluator()
        result = ev.evaluate({"claims": [], "citations": [], "artifact_ids": []})
        assert result["passed"] is True


# ── Hallucination Evaluator ──────────────────────────────────────


class TestHallucinationEvaluator:
    def test_hedged_language_passes(self):
        ev = HallucinationEvaluator()
        record = {
            "claims": [{
                "claim_id": "c1",
                "statement": "Risk signal: this may indicate a potential pattern of concern.",
                "claim_type": "risk_signal",
            }],
        }
        result = ev.evaluate(record)
        assert result["passed"] is True

    def test_absolute_certainty_fails(self):
        ev = HallucinationEvaluator()
        record = {
            "claims": [{
                "claim_id": "c1",
                "statement": "This definitely proves the vendor committed fraud.",
                "claim_type": "finding",
            }],
        }
        result = ev.evaluate(record)
        assert result["passed"] is False
        assert result["detail"]["violation_count"] > 0

    def test_empty_claims_passes(self):
        ev = HallucinationEvaluator()
        result = ev.evaluate({"claims": []})
        assert result["passed"] is True


# ── Determinism Evaluator ────────────────────────────────────────


class TestDeterminismEvaluator:
    def test_identical_hashes_pass(self):
        ev = DeterminismEvaluator(min_runs=3)
        record = {
            "pack_hashes": ["abc123", "abc123", "abc123"],
            "claims_per_run": [["c1", "c2"], ["c1", "c2"], ["c1", "c2"]],
        }
        result = ev.evaluate(record)
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_different_hashes_fail(self):
        ev = DeterminismEvaluator(min_runs=3)
        record = {
            "pack_hashes": ["abc123", "abc123", "def456"],
        }
        result = ev.evaluate(record)
        assert result["passed"] is False
        assert result["score"] < 1.0

    def test_insufficient_runs_fail(self):
        ev = DeterminismEvaluator(min_runs=3)
        record = {"pack_hashes": ["abc123", "abc123"]}
        result = ev.evaluate(record)
        assert result["passed"] is False
        assert result["detail"]["reason"] == "insufficient_runs"

    def test_claim_count_variance_fails(self):
        ev = DeterminismEvaluator(min_runs=3)
        record = {
            "pack_hashes": ["abc123", "abc123", "abc123"],
            "claims_per_run": [["c1", "c2"], ["c1", "c2", "c3"], ["c1", "c2"]],
        }
        result = ev.evaluate(record)
        assert result["passed"] is False


# ── Synthetic Fraud Generator ────────────────────────────────────


class TestSyntheticFraudGenerator:
    def test_seeded_generates_deterministic(self):
        gen = SyntheticFraudGenerator(seed=42)
        ds1 = gen.generate_dataset(n_scenarios=5)
        gen2 = SyntheticFraudGenerator(seed=42)
        ds2 = gen2.generate_dataset(n_scenarios=5)
        assert len(ds1) == len(ds2)
        for s1, s2 in zip(ds1, ds2, strict=False):
            assert s1["scenario_type"] == s2["scenario_type"]
            assert len(s1["vendors"]) == len(s2["vendors"])

    def test_shell_company_network(self):
        gen = SyntheticFraudGenerator(seed=1)
        scenario = gen.generate_shell_company_network(depth=3)
        assert isinstance(scenario, SyntheticFraudScenario)
        assert len(scenario.vendors) >= 3
        assert any("shell" in s or "layer" in s for s in scenario.expected_risk_signals)
        assert len(scenario.relationships) > 0

    def test_bid_rigging_scenario(self):
        gen = SyntheticFraudGenerator(seed=2)
        scenario = gen.generate_bid_rigging_scenario(vendor_count=4)
        assert isinstance(scenario, SyntheticFraudScenario)
        assert len(scenario.vendors) == 4
        assert len(scenario.awards) > 0

    def test_dataset_uses_synthetic_names(self):
        gen = SyntheticFraudGenerator(seed=99)
        ds = gen.generate_dataset(n_scenarios=3)
        for record in ds:
            for vendor in record["vendors"]:
                assert vendor["canonical_name"]  # Not empty
                assert "Lockheed" not in vendor["canonical_name"]
                assert "Boeing" not in vendor["canonical_name"]


# ── Release Gates ────────────────────────────────────────────────


class TestReleaseGates:
    def test_all_gates_pass(self):
        result = check_gates({
            "grounding_rate": 0.98,
            "citation_validity": 1.0,
            "hallucination_block_rate": 0.97,
            "retrieval_recall_at_10": 0.85,
            "replay_determinism": True,
            "cost_per_case_usd": 0.23,
            "coverage_percent": 85,
        })
        assert result["passed"] is True
        assert "All release gates passed" in result["summary"]

    def test_grounding_below_threshold_fails(self):
        result = check_gates({
            "grounding_rate": 0.80,
            "citation_validity": 1.0,
            "hallucination_block_rate": 0.97,
            "retrieval_recall_at_10": 0.85,
            "replay_determinism": True,
            "cost_per_case_usd": 0.23,
            "coverage_percent": 85,
        })
        assert result["passed"] is False
        failed = [g["gate"] for g in result["gate_results"] if not g["passed"]]
        assert "grounding_rate" in failed

    def test_cost_over_threshold_fails(self):
        result = check_gates({
            "grounding_rate": 0.98,
            "citation_validity": 1.0,
            "hallucination_block_rate": 0.97,
            "retrieval_recall_at_10": 0.85,
            "replay_determinism": True,
            "cost_per_case_usd": 2.50,
            "coverage_percent": 85,
        })
        assert result["passed"] is False
        failed = [g["gate"] for g in result["gate_results"] if not g["passed"]]
        assert "cost_per_case_usd" in failed

    def test_non_deterministic_fails(self):
        result = check_gates({
            "grounding_rate": 0.98,
            "citation_validity": 1.0,
            "hallucination_block_rate": 0.97,
            "retrieval_recall_at_10": 0.85,
            "replay_determinism": False,
            "cost_per_case_usd": 0.23,
            "coverage_percent": 85,
        })
        assert result["passed"] is False
        failed = [g["gate"] for g in result["gate_results"] if not g["passed"]]
        assert "replay_determinism" in failed

    def test_default_thresholds(self):
        assert RELEASE_GATES.grounding_rate_min == 0.95
        assert RELEASE_GATES.citation_validity_min == 1.0
        assert RELEASE_GATES.hallucination_block_rate_min == 0.95
        assert RELEASE_GATES.replay_determinism is True
        assert RELEASE_GATES.max_cost_per_case_usd == 1.00
        assert RELEASE_GATES.min_coverage_percent == 80


# ── Eval Harness Integration ────────────────────────────────────


class TestEvalHarness:
    def test_harness_runs_evaluators(self):
        harness = EvalHarness("test_suite")
        harness.register(GroundingEvaluator())

        dataset = [
            {
                "case_id": "case-001",
                "claims": [{"claim_id": "c1", "claim_type": "finding"}],
                "citations": [{"claim_id": "c1", "artifact_id": "art-001"}],
                "artifact_ids": ["art-001"],
            }
        ]
        report = harness.run(dataset)
        assert isinstance(report, EvalReport)
        assert report.total == 1
        assert report.passed == 1
        assert report.pass_rate == 1.0

    def test_harness_multiple_evaluators(self):
        harness = EvalHarness("multi_suite")
        harness.register(GroundingEvaluator())
        harness.register(HallucinationEvaluator())

        dataset = [{
            "case_id": "case-001",
            "claims": [{
                "claim_id": "c1",
                "claim_type": "risk_signal",
                "statement": "Risk signal: this may indicate a potential issue.",
            }],
            "citations": [{"claim_id": "c1", "artifact_id": "art-001"}],
            "artifact_ids": ["art-001"],
        }]
        report = harness.run(dataset)
        assert report.total == 2  # 1 record × 2 evaluators
        assert report.passed == 2
