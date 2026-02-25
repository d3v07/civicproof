from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    evaluator: str
    case_id: str | None
    passed: bool
    score: float | None
    detail: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class EvalReport:
    suite: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    results: list[EvalResult]
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "duration_ms": self.duration_ms,
            "results": [
                {
                    "evaluator": r.evaluator,
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "score": r.score,
                    "detail": r.detail,
                    "duration_ms": r.duration_ms,
                }
                for r in self.results
            ],
        }


class EvalHarness:
    def __init__(self, suite_name: str) -> None:
        self._suite_name = suite_name
        self._evaluators: list[Any] = []

    def register(self, evaluator: Any) -> EvalHarness:
        self._evaluators.append(evaluator)
        return self

    def run(self, dataset: list[dict[str, Any]]) -> EvalReport:
        results: list[EvalResult] = []
        suite_start = time.perf_counter()

        for evaluator in self._evaluators:
            for record in dataset:
                case_id = record.get("case_id")
                start = time.perf_counter()
                try:
                    eval_result = evaluator.evaluate(record)
                    duration_ms = (time.perf_counter() - start) * 1000
                    results.append(
                        EvalResult(
                            evaluator=getattr(evaluator, "name", type(evaluator).__name__),
                            case_id=case_id,
                            passed=eval_result.get("passed", False),
                            score=eval_result.get("score"),
                            detail=eval_result.get("detail", {}),
                            duration_ms=duration_ms,
                        )
                    )
                except Exception as exc:
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.error(
                        "evaluator %s failed on case_id=%s: %s",
                        type(evaluator).__name__,
                        case_id,
                        exc,
                    )
                    results.append(
                        EvalResult(
                            evaluator=getattr(evaluator, "name", type(evaluator).__name__),
                            case_id=case_id,
                            passed=False,
                            score=0.0,
                            detail={"error": str(exc)},
                            duration_ms=duration_ms,
                        )
                    )

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = passed / total if total > 0 else 0.0
        suite_duration_ms = (time.perf_counter() - suite_start) * 1000

        report = EvalReport(
            suite=self._suite_name,
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
            results=results,
            duration_ms=suite_duration_ms,
        )

        logger.info(
            "eval_complete suite=%s total=%d passed=%d pass_rate=%.2f duration_ms=%.1f",
            self._suite_name,
            total,
            passed,
            pass_rate,
            suite_duration_ms,
        )
        return report

    async def run_async(self, dataset: list[dict[str, Any]]) -> EvalReport:
        import asyncio
        results: list[EvalResult] = []
        suite_start = time.perf_counter()

        for evaluator in self._evaluators:
            for record in dataset:
                case_id = record.get("case_id")
                start = time.perf_counter()
                try:
                    if asyncio.iscoroutinefunction(evaluator.evaluate):
                        eval_result = await evaluator.evaluate(record)
                    else:
                        eval_result = evaluator.evaluate(record)
                    duration_ms = (time.perf_counter() - start) * 1000
                    results.append(
                        EvalResult(
                            evaluator=getattr(evaluator, "name", type(evaluator).__name__),
                            case_id=case_id,
                            passed=eval_result.get("passed", False),
                            score=eval_result.get("score"),
                            detail=eval_result.get("detail", {}),
                            duration_ms=duration_ms,
                        )
                    )
                except Exception as exc:
                    duration_ms = (time.perf_counter() - start) * 1000
                    results.append(
                        EvalResult(
                            evaluator=getattr(evaluator, "name", type(evaluator).__name__),
                            case_id=case_id,
                            passed=False,
                            score=0.0,
                            detail={"error": str(exc)},
                            duration_ms=duration_ms,
                        )
                    )

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        suite_duration_ms = (time.perf_counter() - suite_start) * 1000
        return EvalReport(
            suite=self._suite_name,
            total=total,
            passed=passed,
            failed=total - passed,
            pass_rate=passed / total if total > 0 else 0.0,
            results=results,
            duration_ms=suite_duration_ms,
        )
