"""Tests for the eval harness, evaluators, synthetic generators, and release gates.

Covers: GroundingEvaluator, HallucinationEvaluator, RetrievalEvaluator,
DeterminismEvaluator, SyntheticFraudGenerator, EvalHarness, check_gates.
"""
from __future__ import annotations

import pytest
from civicproof_eval.config import RELEASE_GATES, check_gates
from civicproof_eval.evaluators.determinism import DeterminismEvaluator
from civicproof_eval.evaluators.grounding import GroundingEvaluator
from civicproof_eval.evaluators.hallucination import HallucinationEvaluator
from civicproof_eval.evaluators.retrieval import RetrievalEvaluator
from civicproof_eval.generators.synthetic_fraud import SyntheticFraudGenerator
from civicproof_eval.harness import EvalHarness

# ── Grounding Evaluator ─────────────────────────────────────────────────


class TestGroundingEvaluator:
    @pytest.fixture
    def evaluator(self):
        return GroundingEvaluator()

    def test_no_claims_passes(self, evaluator):
        result = evaluator.evaluate({"claims": []})
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_all_claims_cited_passes(self, evaluator):
        result = evaluator.evaluate({
            "claims": [
                {"claim_id": "c1", "claim_type": "finding"},
                {"claim_id": "c2", "claim_type": "risk_signal"},
            ],
            "citations": [
                {"claim_id": "c1", "artifact_id": "a1"},
                {"claim_id": "c2", "artifact_id": "a2"},
            ],
            "artifact_ids": ["a1", "a2"],
        })
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_uncited_claim_fails(self, evaluator):
        result = evaluator.evaluate({
            "claims": [
                {"claim_id": "c1", "claim_type": "finding"},
                {"claim_id": "c2", "claim_type": "finding"},
            ],
            "citations": [
                {"claim_id": "c1", "artifact_id": "a1"},
            ],
            "artifact_ids": ["a1"],
        })
        assert result["passed"] is False
        assert result["score"] == 0.5
        assert "c2" in result["detail"]["uncited_claim_ids"]

    def test_invalid_citation_fails(self, evaluator):
        result = evaluator.evaluate({
            "claims": [{"claim_id": "c1", "claim_type": "finding"}],
            "citations": [{"claim_id": "c1", "artifact_id": "FAKE"}],
            "artifact_ids": ["a1"],
        })
        assert result["passed"] is False
        assert "FAKE" in result["detail"]["invalid_citation_artifact_ids"]

    def test_cannot_conclude_claims_tracked(self, evaluator):
        result = evaluator.evaluate({
            "claims": [
                {"claim_id": "c1", "claim_type": "cannot_conclude"},
            ],
            "citations": [{"claim_id": "c1", "artifact_id": "a1"}],
            "artifact_ids": ["a1"],
        })
        assert result["detail"]["cannot_conclude_count"] == 1


# ── Hallucination Evaluator ──────────────────────────────────────────────


class TestHallucinationEvaluator:
    @pytest.fixture
    def evaluator(self):
        return HallucinationEvaluator()

    def test_no_claims_passes(self, evaluator):
        result = evaluator.evaluate({"claims": []})
        assert result["passed"] is True

    def test_hedged_claim_passes(self, evaluator):
        result = evaluator.evaluate({
            "claims": [{
                "claim_id": "c1",
                "statement": "Risk signal: potential irregularity suggests further investigation.",
                "claim_type": "risk_signal",
            }],
        })
        assert result["passed"] is True

    def test_absolute_certainty_fails(self, evaluator):
        result = evaluator.evaluate({
            "claims": [{
                "claim_id": "c1",
                "statement": "The vendor definitely committed fraud.",
                "claim_type": "finding",
            }],
        })
        assert result["passed"] is False
        assert result["detail"]["violation_count"] > 0

    def test_unhedged_factual_fails(self, evaluator):
        result = evaluator.evaluate({
            "claims": [{
                "claim_id": "c1",
                "statement": "The vendor received contracts worth $5M.",
                "claim_type": "finding",
            }],
        })
        assert result["passed"] is False
        assert "c1" in result["detail"]["unhedged_claim_ids"]

    def test_auditor_rejected_claim_counted(self, evaluator):
        result = evaluator.evaluate({
            "claims": [{
                "claim_id": "c1",
                "statement": "This is fine.",
                "claim_type": "finding",
                "audit_passed": False,
            }],
        })
        assert result["passed"] is False
        assert result["detail"]["violation_count"] == 1

    def test_multiple_claims_mixed(self, evaluator):
        result = evaluator.evaluate({
            "claims": [
                {
                    "claim_id": "c1",
                    "statement": "Risk signal: may indicate potential issues.",
                    "claim_type": "risk_signal",
                },
                {
                    "claim_id": "c2",
                    "statement": "This proves the vendor is guilty.",
                    "claim_type": "finding",
                },
            ],
        })
        assert result["passed"] is False
        assert result["score"] == 0.5


# ── Retrieval Evaluator ──────────────────────────────────────────────────


class TestRetrievalEvaluator:
    @pytest.fixture
    def evaluator(self):
        return RetrievalEvaluator(k=5)

    def test_no_relevant_set_passes(self, evaluator):
        result = evaluator.evaluate({"retrieved_artifact_ids": ["a1"]})
        assert result["passed"] is True

    def test_perfect_recall(self, evaluator):
        result = evaluator.evaluate({
            "retrieved_artifact_ids": ["a1", "a2", "a3"],
            "relevant_artifact_ids": ["a1", "a2", "a3"],
        })
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_low_recall_fails(self, evaluator):
        result = evaluator.evaluate({
            "retrieved_artifact_ids": ["a1"],
            "relevant_artifact_ids": ["a1", "a2", "a3", "a4", "a5"],
        })
        assert result["passed"] is False
        assert result["score"] == 0.2

    def test_recall_at_k_threshold(self, evaluator):
        result = evaluator.evaluate({
            "retrieved_artifact_ids": ["a1", "a2", "a3", "a4"],
            "relevant_artifact_ids": ["a1", "a2", "a3", "a4", "a5"],
        })
        assert result["passed"] is True
        assert result["score"] == 0.8

    def test_precision_computed(self, evaluator):
        result = evaluator.evaluate({
            "retrieved_artifact_ids": ["a1", "x1", "x2", "x3", "x4"],
            "relevant_artifact_ids": ["a1"],
        })
        detail = result["detail"]
        assert detail["precision@5"] == 0.2
        assert detail["recall@5"] == 1.0

    def test_empty_retrieved_zero_precision(self, evaluator):
        result = evaluator.evaluate({
            "retrieved_artifact_ids": [],
            "relevant_artifact_ids": ["a1", "a2"],
        })
        assert result["passed"] is False
        assert result["score"] == 0.0


# ── Determinism Evaluator ────────────────────────────────────────────────


class TestDeterminismEvaluator:
    @pytest.fixture
    def evaluator(self):
        return DeterminismEvaluator(min_runs=3)

    def test_identical_hashes_passes(self, evaluator):
        result = evaluator.evaluate({
            "case_id": "test",
            "pack_hashes": ["abc", "abc", "abc"],
        })
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_different_hashes_fails(self, evaluator):
        result = evaluator.evaluate({
            "case_id": "test",
            "pack_hashes": ["abc", "abc", "def"],
        })
        assert result["passed"] is False
        assert result["detail"]["unique_hashes"] == 2

    def test_insufficient_runs_fails(self, evaluator):
        result = evaluator.evaluate({
            "case_id": "test",
            "pack_hashes": ["abc", "abc"],
        })
        assert result["passed"] is False
        assert result["detail"]["reason"] == "insufficient_runs"

    def test_claim_count_variance_fails(self, evaluator):
        result = evaluator.evaluate({
            "case_id": "test",
            "pack_hashes": ["abc", "abc", "abc"],
            "claims_per_run": [["c1"], ["c1", "c2"], ["c1"]],
        })
        assert result["passed"] is False
        assert result["detail"]["claim_count_variance"] == 1

    def test_single_hash_all_same(self, evaluator):
        result = evaluator.evaluate({
            "case_id": "test",
            "pack_hashes": ["x", "x", "x", "x", "x"],
        })
        assert result["passed"] is True
        assert result["detail"]["total_runs"] == 5


# ── Synthetic Fraud Generator ────────────────────────────────────────────


class TestSyntheticFraudGenerator:
    def test_shell_company_scenario(self):
        gen = SyntheticFraudGenerator(seed=42)
        scenario = gen.generate_shell_company_network(depth=3)
        assert scenario.scenario_type == "shell_company_network"
        assert len(scenario.vendors) == 4  # root + 3 layers
        assert len(scenario.awards) >= 2
        assert len(scenario.relationships) == 3
        assert any("shell" in s for s in scenario.expected_risk_signals)

    def test_bid_rigging_scenario(self):
        gen = SyntheticFraudGenerator(seed=42)
        scenario = gen.generate_bid_rigging_scenario(vendor_count=4)
        assert scenario.scenario_type == "bid_rigging"
        assert len(scenario.vendors) == 4
        assert len(scenario.awards) == 1
        assert len(scenario.relationships) == 4

    def test_generate_dataset(self):
        gen = SyntheticFraudGenerator(seed=42)
        dataset = gen.generate_dataset(n_scenarios=10)
        assert len(dataset) == 10
        types = {r["scenario_type"] for r in dataset}
        assert "shell_company_network" in types
        assert "bid_rigging" in types

    def test_dataset_has_required_fields(self):
        gen = SyntheticFraudGenerator(seed=42)
        dataset = gen.generate_dataset(n_scenarios=2)
        for record in dataset:
            assert "case_id" in record
            assert "vendors" in record
            assert "awards" in record
            assert "relationships" in record
            assert "expected_risk_signals" in record

    def test_structural_determinism(self):
        gen = SyntheticFraudGenerator(seed=99)
        s = gen.generate_shell_company_network(depth=2)
        # Vendor count is deterministic by depth (root + 2 layers = 3)
        assert len(s.vendors) == 3
        # Relationship count matches layers
        assert len(s.relationships) == 2
        # Root vendor is not a shell
        assert s.vendors[0].is_shell is False
        # All subsequent vendors are shells
        assert all(v.is_shell for v in s.vendors[1:])


# ── Eval Harness ─────────────────────────────────────────────────────────


class TestEvalHarness:
    def test_harness_runs_evaluators(self):
        harness = EvalHarness("test_suite")
        harness.register(GroundingEvaluator())
        dataset = [{
            "case_id": "c1",
            "claims": [{"claim_id": "cl1", "claim_type": "finding"}],
            "citations": [{"claim_id": "cl1", "artifact_id": "a1"}],
            "artifact_ids": ["a1"],
        }]
        report = harness.run(dataset)
        assert report.suite == "test_suite"
        assert report.total == 1
        assert report.passed == 1
        assert report.pass_rate == 1.0

    def test_harness_multiple_evaluators(self):
        harness = EvalHarness("multi")
        harness.register(GroundingEvaluator())
        harness.register(DeterminismEvaluator(min_runs=2))
        dataset = [{
            "case_id": "c1",
            "claims": [],
            "pack_hashes": ["a", "a"],
        }]
        report = harness.run(dataset)
        assert report.total == 2
        assert report.passed == 2

    def test_harness_with_failing_evaluator(self):
        harness = EvalHarness("fail_test")
        harness.register(GroundingEvaluator())
        dataset = [{
            "case_id": "c1",
            "claims": [{"claim_id": "cl1", "claim_type": "finding"}],
            "citations": [],
            "artifact_ids": [],
        }]
        report = harness.run(dataset)
        assert report.failed == 1
        assert report.pass_rate == 0.0

    def test_harness_report_to_dict(self):
        harness = EvalHarness("dict_test")
        harness.register(GroundingEvaluator())
        report = harness.run([{"case_id": "c1", "claims": []}])
        d = report.to_dict()
        assert d["suite"] == "dict_test"
        assert isinstance(d["results"], list)
        assert d["results"][0]["evaluator"] == "grounding"

    @pytest.mark.asyncio
    async def test_harness_run_async(self):
        harness = EvalHarness("async_test")
        harness.register(GroundingEvaluator())
        report = await harness.run_async([{"case_id": "c1", "claims": []}])
        assert report.total == 1
        assert report.passed == 1

    def test_harness_evaluator_exception_handled(self):
        class BrokenEvaluator:
            name = "broken"
            def evaluate(self, record):
                raise RuntimeError("eval crash")

        harness = EvalHarness("broken_test")
        harness.register(BrokenEvaluator())
        report = harness.run([{"case_id": "c1"}])
        assert report.total == 1
        assert report.failed == 1
        assert "error" in report.results[0].detail


# ── Release Gates ────────────────────────────────────────────────────────


class TestReleaseGates:
    def test_all_gates_pass(self):
        results = {
            "grounding_rate": 0.98,
            "citation_validity": 1.0,
            "hallucination_block_rate": 0.97,
            "retrieval_recall_at_10": 0.85,
            "replay_determinism": True,
            "cost_per_case_usd": 0.45,
            "coverage_percent": 82,
        }
        gate_result = check_gates(results)
        assert gate_result["passed"] is True
        assert "All release gates passed" in gate_result["summary"]

    def test_grounding_gate_fails(self):
        results = {
            "grounding_rate": 0.90,  # below 0.95 threshold
            "citation_validity": 1.0,
            "hallucination_block_rate": 0.97,
            "retrieval_recall_at_10": 0.85,
            "replay_determinism": True,
            "cost_per_case_usd": 0.45,
            "coverage_percent": 82,
        }
        gate_result = check_gates(results)
        assert gate_result["passed"] is False
        assert "grounding_rate" in gate_result["summary"]

    def test_cost_gate_fails(self):
        results = {
            "grounding_rate": 0.98,
            "citation_validity": 1.0,
            "hallucination_block_rate": 0.97,
            "retrieval_recall_at_10": 0.85,
            "replay_determinism": True,
            "cost_per_case_usd": 1.50,  # above $1.00 max
            "coverage_percent": 82,
        }
        gate_result = check_gates(results)
        assert gate_result["passed"] is False
        failed = [g for g in gate_result["gate_results"] if not g["passed"]]
        assert any(g["gate"] == "cost_per_case_usd" for g in failed)

    def test_multiple_gates_fail(self):
        results = {
            "grounding_rate": 0.50,
            "citation_validity": 0.80,
            "hallucination_block_rate": 0.50,
            "retrieval_recall_at_10": 0.50,
            "replay_determinism": False,
            "cost_per_case_usd": 5.00,
            "coverage_percent": 30,
        }
        gate_result = check_gates(results)
        assert gate_result["passed"] is False
        failed = [g for g in gate_result["gate_results"] if not g["passed"]]
        assert len(failed) == 7

    def test_defaults_from_frozen_dataclass(self):
        assert RELEASE_GATES.grounding_rate_min == 0.95
        assert RELEASE_GATES.min_coverage_percent == 80
        assert RELEASE_GATES.replay_determinism is True

    def test_missing_results_default_to_zero(self):
        gate_result = check_gates({})
        assert gate_result["passed"] is False
        failed = [g for g in gate_result["gate_results"] if not g["passed"]]
        assert len(failed) >= 5
