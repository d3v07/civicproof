"""Anomaly Detector Agent.

Runs all 6 deterministic anomaly detection rules against case data
and produces composite risk scores with citations to supporting artifacts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from civicproof_common.anomalies.rules import (
    AnomalyResult,
    detect_all_anomalies,
)
from civicproof_common.db.models import EntityModel, RawArtifactModel

logger = logging.getLogger(__name__)


@dataclass
class RiskSignal:
    """A risk signal produced by the anomaly detector."""

    signal_type: str
    severity: str
    score: float
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)
    affected_entity_ids: list[str] = field(default_factory=list)
    supporting_artifact_ids: list[str] = field(default_factory=list)


@dataclass
class AnomalyDetectionResult:
    """Complete result from the anomaly detector agent."""

    risk_signals: list[RiskSignal] = field(default_factory=list)
    composite_risk_score: float = 0.0
    detection_log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_risk(self) -> bool:
        return len(self.risk_signals) > 0


class AnomalyDetectorAgent:
    """Runs all anomaly detectors and produces risk signals."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def detect(
        self,
        entity_id: str,
        awards: list[dict[str, Any]],
        entities: list[dict[str, Any]] | None = None,
        entity_officers: dict[str, list[str]] | None = None,
        vendor_location: dict[str, Any] | None = None,
        performance_location: dict[str, Any] | None = None,
    ) -> AnomalyDetectionResult:
        """Run all anomaly detectors against case data.

        Args:
            entity_id: The primary entity ID.
            awards: List of award dicts for the entity.
            entities: Optional list of entity dicts for ring detection.
            entity_officers: Optional mapping of entity_id -> officer names.
            vendor_location: Optional vendor location dict.
            performance_location: Optional performance location dict.

        Returns:
            AnomalyDetectionResult with risk signals and composite score.
        """
        result = AnomalyDetectionResult()

        # Run all detectors
        anomalies = detect_all_anomalies(
            awards=awards,
            vendor_id=entity_id,
            entities=entities,
            entity_officers=entity_officers,
            vendor_location=vendor_location,
            performance_location=performance_location,
        )

        # Convert anomaly results to risk signals
        for anomaly in anomalies:
            signal = RiskSignal(
                signal_type=anomaly.anomaly_type,
                severity=anomaly.severity,
                score=anomaly.score,
                description=anomaly.description,
                evidence=anomaly.evidence,
                affected_entity_ids=anomaly.affected_entity_ids,
                supporting_artifact_ids=anomaly.affected_artifact_ids,
            )
            result.risk_signals.append(signal)

        # Compute composite risk score
        if result.risk_signals:
            severity_weights = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
            weighted_scores = [
                s.score * severity_weights.get(s.severity, 0.3)
                for s in result.risk_signals
            ]
            result.composite_risk_score = min(
                sum(weighted_scores) / max(len(weighted_scores), 1), 1.0
            )

        result.detection_log.append({
            "action": "anomaly_detection_complete",
            "signals_found": len(result.risk_signals),
            "composite_score": result.composite_risk_score,
            "detectors_run": 6,
        })

        return result
