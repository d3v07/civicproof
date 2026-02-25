"""Anomaly detection rules library.

All 6 detectors are DETERMINISTIC rule-based — no LLM calls.
Each detector operates on structured award/entity data and produces
typed risk signals with severity levels.
"""

from .rules import (
    AnomalyResult,
    detect_all_anomalies,
    detect_geographic_mismatch,
    detect_modification_inflation,
    detect_officer_overlap,
    detect_rapid_awarding,
    detect_shared_address_ring,
    detect_sole_source_concentration,
)

__all__ = [
    "AnomalyResult",
    "detect_all_anomalies",
    "detect_geographic_mismatch",
    "detect_modification_inflation",
    "detect_officer_overlap",
    "detect_rapid_awarding",
    "detect_shared_address_ring",
    "detect_sole_source_concentration",
]
