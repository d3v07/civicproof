"""Unit tests for the 6 deterministic anomaly detection rules.

All detectors are pure functions — same input always produces same output.
No mocking needed.
"""


from civicproof_common.anomalies.rules import (
    detect_all_anomalies,
    detect_geographic_mismatch,
    detect_modification_inflation,
    detect_officer_overlap,
    detect_rapid_awarding,
    detect_shared_address_ring,
    detect_sole_source_concentration,
)

# ── 1. Sole-source concentration ──────────────────────────────────


class TestSoleSourceConcentration:
    def test_high_concentration_detected(self):
        awards = [
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "NOT COMPETED"}
            for _ in range(10)
        ]
        result = detect_sole_source_concentration(awards, "v1", threshold=0.80)
        assert result.detected is True
        assert result.severity in ("medium", "high")
        assert result.score >= 0.80

    def test_competed_awards_not_flagged(self):
        awards = [
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "FULL AND OPEN"}
            for _ in range(10)
        ]
        result = detect_sole_source_concentration(awards, "v1", threshold=0.80)
        assert result.detected is False

    def test_below_threshold_not_flagged(self):
        awards = [
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "NOT COMPETED"},
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "FULL AND OPEN"},
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "FULL AND OPEN"},
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "FULL AND OPEN"},
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "FULL AND OPEN"},
        ]
        result = detect_sole_source_concentration(awards, "v1", threshold=0.80)
        assert result.detected is False

    def test_empty_awards(self):
        result = detect_sole_source_concentration([], "v1")
        assert result.detected is False


# ── 2. Modification inflation ──────────────────────────────────────


class TestModificationInflation:
    def test_significant_inflation_detected(self):
        award = {"original_amount": 1_000_000, "current_amount": 2_500_000}
        result = detect_modification_inflation(award, threshold=0.50)
        assert result.detected is True
        assert result.evidence["inflation_ratio"] == 1.5

    def test_minor_increase_not_flagged(self):
        award = {"original_amount": 1_000_000, "current_amount": 1_200_000}
        result = detect_modification_inflation(award, threshold=0.50)
        assert result.detected is False

    def test_zero_original_amount(self):
        award = {"original_amount": 0, "current_amount": 500_000}
        result = detect_modification_inflation(award, threshold=0.50)
        assert result.detected is False

    def test_high_severity_for_3x_inflation(self):
        award = {"original_amount": 100_000, "current_amount": 350_000}
        result = detect_modification_inflation(award, threshold=0.50)
        assert result.detected is True
        assert result.severity in ("low", "medium", "high")


# ── 3. Geographic mismatch ────────────────────────────────────────


class TestGeographicMismatch:
    def test_same_state_not_flagged(self):
        vendor = {"state": "VA"}
        perf = {"state": "VA"}
        result = detect_geographic_mismatch(vendor, perf, threshold_miles=1000)
        assert result.detected is False

    def test_distant_states_flagged(self):
        vendor = {"state": "CA"}
        perf = {"state": "NY"}
        result = detect_geographic_mismatch(vendor, perf, threshold_miles=1000)
        assert result.detected is True

    def test_coordinates_same_location(self):
        vendor = {"latitude": 38.9, "longitude": -77.0}
        perf = {"latitude": 38.9, "longitude": -77.0}
        result = detect_geographic_mismatch(vendor, perf, threshold_miles=1000)
        assert result.detected is False

    def test_coordinates_distant_locations(self):
        vendor = {"latitude": 34.0, "longitude": -118.2}  # LA
        perf = {"latitude": 40.7, "longitude": -74.0}     # NYC
        result = detect_geographic_mismatch(vendor, perf, threshold_miles=1000)
        assert result.detected is True

    def test_missing_location_data(self):
        result = detect_geographic_mismatch({}, {}, threshold_miles=1000)
        assert result.detected is False


# ── 4. Rapid awarding ─────────────────────────────────────────────


class TestRapidAwarding:
    def test_many_awards_in_window(self):
        awards = [
            {"vendor_id": "v1", "start_date": f"2025-01-{i+1:02d}"}
            for i in range(5)
        ]
        result = detect_rapid_awarding(awards, "v1", window_days=30, min_awards=3)
        assert result.detected is True
        assert result.evidence["max_awards_in_window"] == 5

    def test_spread_awards_not_flagged(self):
        awards = [
            {"vendor_id": "v1", "start_date": "2025-01-01"},
            {"vendor_id": "v1", "start_date": "2025-04-01"},
            {"vendor_id": "v1", "start_date": "2025-07-01"},
        ]
        result = detect_rapid_awarding(awards, "v1", window_days=30, min_awards=3)
        assert result.detected is False

    def test_insufficient_awards(self):
        awards = [{"vendor_id": "v1", "start_date": "2025-01-01"}]
        result = detect_rapid_awarding(awards, "v1", window_days=30, min_awards=3)
        assert result.detected is False


# ── 5. Shared address ring ────────────────────────────────────────


class TestSharedAddressRing:
    def test_ring_detected(self):
        entities = [
            {
                "entity_id": f"e{i}",
                "canonical_name": f"Vendor {i}",
                "address": "123 Main St, Suite 100, Anytown, VA",
            }
            for i in range(4)
        ]
        results = detect_shared_address_ring(entities, min_entities=3)
        assert len(results) == 1
        assert results[0].detected is True
        assert results[0].evidence["entity_count"] == 4

    def test_unique_addresses_not_flagged(self):
        entities = [
            {"entity_id": "e1", "canonical_name": "A", "address": "111 First St"},
            {"entity_id": "e2", "canonical_name": "B", "address": "222 Second St"},
            {"entity_id": "e3", "canonical_name": "C", "address": "333 Third St"},
        ]
        results = detect_shared_address_ring(entities, min_entities=3)
        assert len(results) == 0

    def test_empty_entities(self):
        results = detect_shared_address_ring([], min_entities=3)
        assert len(results) == 0


# ── 6. Officer overlap ───────────────────────────────────────────


class TestOfficerOverlap:
    def test_overlap_detected(self):
        entity_officers = {
            "e1": ["John Smith", "Jane Doe"],
            "e2": ["John Smith", "Jane Doe"],
        }
        results = detect_officer_overlap(entity_officers, min_overlap=2)
        assert len(results) >= 1
        assert results[0].detected is True

    def test_no_overlap(self):
        entity_officers = {
            "e1": ["John Smith"],
            "e2": ["Jane Doe"],
        }
        results = detect_officer_overlap(entity_officers, min_overlap=2)
        assert len(results) == 0

    def test_single_shared_below_threshold(self):
        entity_officers = {
            "e1": ["John Smith", "Alice Brown"],
            "e2": ["John Smith", "Bob Green"],
        }
        results = detect_officer_overlap(entity_officers, min_overlap=2)
        assert len(results) == 0


# ── detect_all_anomalies ─────────────────────────────────────────


class TestDetectAll:
    def test_returns_only_detected(self):
        awards = [
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "FULL AND OPEN"}
            for _ in range(3)
        ]
        results = detect_all_anomalies(awards, "v1")
        for r in results:
            assert r.detected is True

    def test_determinism(self):
        awards = [
            {"vendor_id": "v1", "awarding_agency": "DoD", "extent_competed": "NOT COMPETED"}
            for _ in range(5)
        ]
        r1 = detect_all_anomalies(awards, "v1")
        r2 = detect_all_anomalies(awards, "v1")
        assert len(r1) == len(r2)
        assert [a.anomaly_type for a in r1] == [a.anomaly_type for a in r2]
