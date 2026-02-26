"""Six deterministic anomaly detectors for federal procurement fraud signals.

All detectors are pure functions — deterministic, no LLM calls, no network.
Same input always produces the same output.

Detectors:
1. sole_source_concentration — vendor >80% sole-source from single agency
2. modification_inflation   — modifications exceed original value by >50%
3. geographic_mismatch      — vendor address vs place of performance >1000 miles
4. rapid_awarding           — multiple awards to same vendor in <30 days
5. shared_address_ring      — 3+ distinct vendors at same physical address
6. officer_overlap          — same officers across independent vendors
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class AnomalyResult:
    """Result from an anomaly detector."""

    anomaly_type: str
    detected: bool
    severity: str = "none"  # none, low, medium, high, critical
    score: float = 0.0  # 0.0 = no anomaly, 1.0 = maximum severity
    description: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    affected_entity_ids: list[str] = field(default_factory=list)
    affected_artifact_ids: list[str] = field(default_factory=list)

    @property
    def is_risk_signal(self) -> bool:
        return self.detected and self.severity != "none"


def detect_sole_source_concentration(
    awards: list[dict[str, Any]],
    vendor_id: str,
    threshold: float = 0.80,
) -> AnomalyResult:
    """Detect if a vendor receives >threshold sole-source awards from one agency.

    Args:
        awards: List of award dicts with at least 'vendor_id', 'awarding_agency',
                and 'extent_competed' or 'is_sole_source' fields.
        vendor_id: The vendor entity ID to analyze.
        threshold: Fraction threshold for flagging (default 0.80).

    Returns:
        AnomalyResult with detection status and evidence.
    """
    vendor_awards = [a for a in awards if a.get("vendor_id") == vendor_id]
    if not vendor_awards:
        return AnomalyResult(anomaly_type="sole_source_concentration", detected=False)

    # Count sole-source awards by agency
    agency_sole_source: dict[str, int] = {}
    agency_total: dict[str, int] = {}

    for award in vendor_awards:
        agency = award.get("awarding_agency", "unknown")
        agency_total[agency] = agency_total.get(agency, 0) + 1

        is_sole = award.get("is_sole_source", False)
        if not is_sole:
            competed = (award.get("extent_competed") or "").upper()
            sole_codes = {"NOT COMPETED", "SOLE SOURCE", "A", "C", "D", "E", "B"}
            is_sole = competed in sole_codes

        if is_sole:
            agency_sole_source[agency] = agency_sole_source.get(agency, 0) + 1

    # Find worst agency
    worst_agency = ""
    worst_ratio = 0.0
    for agency, total in agency_total.items():
        sole = agency_sole_source.get(agency, 0)
        ratio = sole / total if total > 0 else 0.0
        if ratio > worst_ratio:
            worst_ratio = ratio
            worst_agency = agency

    detected = worst_ratio >= threshold and agency_total.get(worst_agency, 0) >= 3

    severity = "none"
    if detected:
        if worst_ratio >= 0.95:
            severity = "high"
        elif worst_ratio >= 0.90:
            severity = "medium"
        else:
            severity = "low"

    return AnomalyResult(
        anomaly_type="sole_source_concentration",
        detected=detected,
        severity=severity,
        score=worst_ratio,
        description=(
            f"Vendor has {worst_ratio:.0%} sole-source rate from {worst_agency} "
            f"({agency_sole_source.get(worst_agency, 0)}/"
            f"{agency_total.get(worst_agency, 0)} awards)"
            if detected
            else "No sole-source concentration detected"
        ),
        evidence={
            "agency": worst_agency,
            "sole_source_count": agency_sole_source.get(worst_agency, 0),
            "total_awards": agency_total.get(worst_agency, 0),
            "ratio": worst_ratio,
        },
        affected_entity_ids=[vendor_id],
    )


def detect_modification_inflation(
    award: dict[str, Any],
    threshold: float = 0.50,
) -> AnomalyResult:
    """Detect if award modifications exceed original value by >threshold.

    Args:
        award: Award dict with 'original_amount', 'current_amount', and
               optionally 'modifications' list.
        threshold: Inflation threshold (default 0.50 = 50%).

    Returns:
        AnomalyResult with detection status and evidence.
    """
    original = _safe_float(award.get("original_amount", 0))
    current = _safe_float(award.get("current_amount") or award.get("award_amount", 0))

    if original <= 0 or not math.isfinite(original) or not math.isfinite(current):
        return AnomalyResult(
            anomaly_type="modification_inflation", detected=False,
            description="No valid original amount available for comparison",
        )

    inflation_ratio = (current - original) / original

    detected = inflation_ratio > threshold
    modifications = award.get("modifications", [])

    severity = "none"
    if detected:
        if inflation_ratio > 2.0:
            severity = "high"
        elif inflation_ratio > 1.0:
            severity = "medium"
        else:
            severity = "low"

    return AnomalyResult(
        anomaly_type="modification_inflation",
        detected=detected,
        severity=severity,
        score=min(inflation_ratio / 2.0, 1.0),
        description=(
            f"Award inflated by {inflation_ratio:.0%}: "
            f"${original:,.2f} → ${current:,.2f} "
            f"({len(modifications)} modifications)"
            if detected
            else "No significant modification inflation"
        ),
        evidence={
            "original_amount": original,
            "current_amount": current,
            "inflation_ratio": inflation_ratio,
            "modification_count": len(modifications),
        },
        affected_artifact_ids=[award.get("award_id", "")],
    )


def detect_geographic_mismatch(
    vendor_location: dict[str, Any],
    performance_location: dict[str, Any],
    threshold_miles: float = 1000.0,
) -> AnomalyResult:
    """Detect if vendor address and place of performance are >threshold miles apart.

    Args:
        vendor_location: Dict with 'latitude', 'longitude' (or 'state').
        performance_location: Dict with 'latitude', 'longitude' (or 'state').
        threshold_miles: Distance threshold (default 1000 miles).

    Returns:
        AnomalyResult with detection status and evidence.
    """
    vendor_lat = _safe_float(vendor_location.get("latitude"))
    vendor_lon = _safe_float(vendor_location.get("longitude"))
    perf_lat = _safe_float(performance_location.get("latitude"))
    perf_lon = _safe_float(performance_location.get("longitude"))

    # If we have coordinates, compute haversine distance
    if vendor_lat and vendor_lon and perf_lat and perf_lon:
        distance = _haversine_miles(vendor_lat, vendor_lon, perf_lat, perf_lon)
    else:
        # Fallback: use state comparison
        vendor_state = (vendor_location.get("state") or "").upper().strip()
        perf_state = (performance_location.get("state") or "").upper().strip()

        if not vendor_state or not perf_state:
            return AnomalyResult(
                anomaly_type="geographic_mismatch", detected=False,
                description="Insufficient location data for comparison",
            )

        if vendor_state == perf_state:
            distance = 0.0
        else:
            # Estimate based on state centroids (rough approximation)
            distance = _estimate_state_distance(vendor_state, perf_state)

    detected = distance > threshold_miles

    severity = "none"
    if detected:
        if distance > 2500:
            severity = "high"
        elif distance > 1500:
            severity = "medium"
        else:
            severity = "low"

    return AnomalyResult(
        anomaly_type="geographic_mismatch",
        detected=detected,
        severity=severity,
        score=min(distance / 3000.0, 1.0),
        description=(
            f"Vendor location ~{distance:.0f} miles from place of performance"
            if detected
            else f"Vendor within {threshold_miles:.0f} miles of performance location"
        ),
        evidence={
            "vendor_location": vendor_location,
            "performance_location": performance_location,
            "distance_miles": distance,
        },
    )


def detect_rapid_awarding(
    awards: list[dict[str, Any]],
    vendor_id: str,
    window_days: int = 30,
    min_awards: int = 3,
) -> AnomalyResult:
    """Detect multiple awards to same vendor within a short time window.

    Args:
        awards: List of award dicts with 'vendor_id' and 'start_date'.
        vendor_id: The vendor entity ID to analyze.
        window_days: Time window in days (default 30).
        min_awards: Minimum number of awards in window to flag (default 3).

    Returns:
        AnomalyResult with detection status and evidence.
    """
    vendor_awards = [a for a in awards if a.get("vendor_id") == vendor_id]

    # Parse dates
    dated_awards = []
    for award in vendor_awards:
        date_str = award.get("start_date") or award.get("action_date", "")
        parsed = _parse_date(date_str)
        if parsed:
            dated_awards.append((parsed, award))

    dated_awards.sort(key=lambda x: x[0])

    if len(dated_awards) < min_awards:
        return AnomalyResult(
            anomaly_type="rapid_awarding", detected=False,
            description=f"Only {len(dated_awards)} dated awards found",
        )

    # Sliding window
    window = timedelta(days=window_days)
    max_count = 0
    max_window_start = None
    max_window_awards = []

    for i in range(len(dated_awards)):
        window_end = dated_awards[i][0] + window
        count = 0
        window_awards = []
        for j in range(i, len(dated_awards)):
            if dated_awards[j][0] <= window_end:
                count += 1
                window_awards.append(dated_awards[j][1])
            else:
                break
        if count > max_count:
            max_count = count
            max_window_start = dated_awards[i][0]
            max_window_awards = window_awards

    detected = max_count >= min_awards

    severity = "none"
    if detected:
        if max_count >= 8:
            severity = "high"
        elif max_count >= 5:
            severity = "medium"
        else:
            severity = "low"

    return AnomalyResult(
        anomaly_type="rapid_awarding",
        detected=detected,
        severity=severity,
        score=min(max_count / 10.0, 1.0),
        description=(
            f"{max_count} awards issued to vendor within {window_days}-day window"
            if detected
            else f"No rapid awarding pattern detected ({max_count} max in window)"
        ),
        evidence={
            "max_awards_in_window": max_count,
            "window_days": window_days,
            "window_start": max_window_start.isoformat() if max_window_start else None,
            "award_ids": [a.get("award_id", "") for a in max_window_awards[:10]],
        },
        affected_entity_ids=[vendor_id],
    )


def detect_shared_address_ring(
    entities: list[dict[str, Any]],
    min_entities: int = 3,
) -> list[AnomalyResult]:
    """Detect 3+ distinct vendors registered at the same physical address.

    Args:
        entities: List of entity dicts with 'entity_id', 'canonical_name',
                  and 'address' or nested location fields.
        min_entities: Minimum entities to form a ring (default 3).

    Returns:
        List of AnomalyResult, one per detected ring.
    """
    address_groups: dict[str, list[dict[str, Any]]] = {}

    for entity in entities:
        addr = _normalize_address(entity)
        if addr:
            address_groups.setdefault(addr, []).append(entity)

    results = []
    for addr, group in address_groups.items():
        if len(group) >= min_entities:
            entity_ids = [e.get("entity_id", "") for e in group]
            entity_names = [e.get("canonical_name", "") for e in group]

            severity = "high" if len(group) >= 5 else "medium"

            results.append(AnomalyResult(
                anomaly_type="shared_address_ring",
                detected=True,
                severity=severity,
                score=min(len(group) / 5.0, 1.0),
                description=(
                    f"{len(group)} vendors share address: {addr[:100]}. "
                    f"Entities: {', '.join(entity_names[:5])}"
                ),
                evidence={
                    "address": addr,
                    "entity_count": len(group),
                    "entity_names": entity_names,
                },
                affected_entity_ids=entity_ids,
            ))

    return results


def detect_officer_overlap(
    entity_officers: dict[str, list[str]],
    min_overlap: int = 2,
) -> list[AnomalyResult]:
    """Detect the same officer/director names across supposedly independent vendors.

    Args:
        entity_officers: Mapping of entity_id -> list of officer names.
        min_overlap: Minimum number of shared officers to flag (default 2).

    Returns:
        List of AnomalyResult, one per detected overlap pair.
    """
    # Build reverse index: officer_name -> set of entity_ids
    officer_entities: dict[str, set[str]] = {}
    for entity_id, officers in entity_officers.items():
        for name in officers:
            normalized = name.upper().strip()
            if normalized:
                officer_entities.setdefault(normalized, set()).add(entity_id)

    # Find officers appearing in multiple entities
    results = []
    seen_pairs: set[tuple[str, ...]] = set()

    for _officer_name, ent_ids in officer_entities.items():
        if len(ent_ids) >= 2:
            pair_key = tuple(sorted(ent_ids))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # Count how many officers overlap between these entities
            overlap_officers = []
            for other_name, other_ids in officer_entities.items():
                if other_ids == ent_ids or ent_ids.issubset(other_ids):
                    overlap_officers.append(other_name)

            if len(overlap_officers) >= min_overlap:
                severity = "high" if len(overlap_officers) >= 3 else "medium"
                results.append(AnomalyResult(
                    anomaly_type="officer_overlap",
                    detected=True,
                    severity=severity,
                    score=min(len(overlap_officers) / 3.0, 1.0),
                    description=(
                        f"{len(overlap_officers)} shared officers across "
                        f"{len(ent_ids)} entities: {', '.join(overlap_officers[:3])}"
                    ),
                    evidence={
                        "shared_officers": overlap_officers,
                        "entity_count": len(ent_ids),
                    },
                    affected_entity_ids=list(ent_ids),
                ))

    return results


def detect_all_anomalies(
    awards: list[dict[str, Any]],
    vendor_id: str,
    entities: list[dict[str, Any]] | None = None,
    entity_officers: dict[str, list[str]] | None = None,
    vendor_location: dict[str, Any] | None = None,
    performance_location: dict[str, Any] | None = None,
) -> list[AnomalyResult]:
    """Run all anomaly detectors and return combined results.

    This is the main entry point for the anomaly detection pipeline.
    """
    results: list[AnomalyResult] = []

    # 1. Sole source concentration
    results.append(detect_sole_source_concentration(awards, vendor_id))

    # 2. Modification inflation (per award)
    for award in awards:
        if award.get("vendor_id") == vendor_id:
            result = detect_modification_inflation(award)
            if result.detected:
                results.append(result)

    # 3. Geographic mismatch
    if vendor_location and performance_location:
        results.append(
            detect_geographic_mismatch(vendor_location, performance_location)
        )

    # 4. Rapid awarding
    results.append(detect_rapid_awarding(awards, vendor_id))

    # 5. Shared address ring
    if entities:
        ring_results = detect_shared_address_ring(entities)
        results.extend(ring_results)

    # 6. Officer overlap
    if entity_officers:
        overlap_results = detect_officer_overlap(entity_officers)
        results.extend(overlap_results)

    return [r for r in results if r.detected]


# ── Utility functions ──────────────────────────────────────────────

def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute haversine distance in miles between two lat/lon points."""
    radius = 3959  # Earth radius in miles
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


# Approximate state centroid coordinates for distance estimation
_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (32.7, -86.7), "AK": (64.0, -153.0), "AZ": (34.3, -111.7),
    "AR": (34.8, -92.2), "CA": (37.2, -119.7), "CO": (38.9, -105.5),
    "CT": (41.6, -72.7), "DE": (38.9, -75.5), "FL": (28.6, -82.4),
    "GA": (32.7, -83.4), "HI": (20.5, -157.5), "ID": (44.4, -114.6),
    "IL": (40.0, -89.2), "IN": (39.9, -86.3), "IA": (42.0, -93.5),
    "KS": (38.5, -98.3), "KY": (37.5, -85.3), "LA": (31.0, -91.9),
    "ME": (45.4, -69.2), "MD": (39.0, -76.7), "MA": (42.2, -71.8),
    "MI": (44.3, -84.5), "MN": (46.3, -94.3), "MS": (32.7, -89.7),
    "MO": (38.6, -92.6), "MT": (47.0, -109.6), "NE": (41.5, -99.8),
    "NV": (39.3, -116.6), "NH": (43.7, -71.6), "NJ": (40.1, -74.7),
    "NM": (34.4, -106.1), "NY": (42.9, -75.5), "NC": (35.5, -79.8),
    "ND": (47.5, -100.5), "OH": (40.4, -82.7), "OK": (35.6, -97.5),
    "OR": (43.9, -120.6), "PA": (40.9, -77.8), "RI": (41.7, -71.5),
    "SC": (33.9, -80.9), "SD": (44.4, -100.2), "TN": (35.8, -86.3),
    "TX": (31.5, -99.3), "UT": (39.3, -111.7), "VT": (44.1, -72.6),
    "VA": (37.5, -78.8), "WA": (47.4, -120.7), "WV": (38.6, -80.6),
    "WI": (44.6, -89.8), "WY": (43.0, -107.6), "DC": (38.9, -77.0),
}


def _estimate_state_distance(state_a: str, state_b: str) -> float:
    """Estimate distance between two states using centroid coordinates."""
    coords_a = _STATE_CENTROIDS.get(state_a)
    coords_b = _STATE_CENTROIDS.get(state_b)
    if coords_a and coords_b:
        return _haversine_miles(coords_a[0], coords_a[1], coords_b[0], coords_b[1])
    return 500.0  # Default estimate if state not found


def _normalize_address(entity: dict[str, Any]) -> str:
    """Normalize an entity's address for deduplication."""
    addr = entity.get("address", "")
    if not addr:
        location = entity.get("location", {})
        if isinstance(location, dict):
            parts = [
                location.get("address_line1", ""),
                location.get("city", ""),
                location.get("state", ""),
                location.get("zip", ""),
            ]
            addr = ", ".join(p for p in parts if p)

    return addr.upper().strip() if addr else ""


def _parse_date(date_str: str) -> datetime | None:
    """Parse a date string to datetime."""
    if not date_str:
        return None
    # Strip trailing Z (UTC indicator) for strptime compatibility
    cleaned = date_str.rstrip("Z")
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None
