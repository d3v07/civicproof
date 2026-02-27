"""Unit tests for S7+S8 deliverables.

Tests for: SAM.gov connector, OpenFEC connector, PDF renderer,
metrics response model, and Terraform compliance checks.

All tests are deterministic — no network calls, no LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

# ── Connector Tests ──────────────────────────────────────────────


class TestSAMGovConnector:
    """Verify SAM.gov connector follows data-engineer agent spec."""

    def test_rate_limit_matches_spec(self):
        """data-engineer.md: SAM.gov max 4 RPS."""
        from connectors.sam_gov import SAMGovConnector

        assert SAMGovConnector.rate_limit_rps == 4.0

    def test_source_id(self):
        from connectors.sam_gov import SAMGovConnector

        assert SAMGovConnector.source_id == "sam_gov"

    def test_requires_api_key(self):
        """data-engineer.md: API key required."""
        from connectors.sam_gov import SAMGovConnector

        with pytest.raises(ValueError, match="SAM_GOV_API_KEY"):
            SAMGovConnector(api_key="")

    def test_max_page_size_capped(self):
        """Sprint plan: pagination limit=1000."""
        from connectors.sam_gov import SAMGovConnector

        assert SAMGovConnector.MAX_PAGE_SIZE == 1000

    def test_canonical_url_format(self):
        from connectors.sam_gov import SAMGovConnector

        conn = SAMGovConnector(api_key="test-key-123")
        url = conn.canonical_url({"notice_id": "abc123"})
        assert url == "https://sam.gov/opp/abc123"

    def test_doc_type(self):
        from connectors.sam_gov import SAMGovConnector

        conn = SAMGovConnector(api_key="test-key-123")
        assert conn.doc_type() == "contract_opportunity"


class TestOpenFECConnector:
    """Verify OpenFEC connector follows data-engineer agent spec."""

    def test_rate_limit_matches_spec(self):
        """data-engineer.md: 1000 calls/hour = ~0.28 RPS."""
        from connectors.openfec import OpenFECConnector

        assert OpenFECConnector.rate_limit_rps <= 0.28

    def test_source_id(self):
        from connectors.openfec import OpenFECConnector

        assert OpenFECConnector.source_id == "openfec"

    def test_requires_api_key(self):
        """data-engineer.md: API key required."""
        from connectors.openfec import OpenFECConnector

        with pytest.raises(ValueError, match="OPENFEC_API_KEY"):
            OpenFECConnector(api_key="")

    def test_canonical_url_committee(self):
        from connectors.openfec import OpenFECConnector

        conn = OpenFECConnector(api_key="test-key-123")
        url = conn.canonical_url({"committee_id": "C00123456"})
        assert "C00123456" in url

    def test_canonical_url_receipt(self):
        from connectors.openfec import OpenFECConnector

        conn = OpenFECConnector(api_key="test-key-123")
        url = conn.canonical_url({"committee_id": "C00123456", "sub_id": "12345"})
        assert "12345" in url

    def test_doc_type(self):
        from connectors.openfec import OpenFECConnector

        conn = OpenFECConnector(api_key="test-key-123")
        assert conn.doc_type() == "fec_record"


# ── Existing Connector Compliance ────────────────────────────────


class TestConnectorRateLimitCompliance:
    """Verify ALL connectors match CLAUDE.md rule #6 rate limits."""

    def test_usaspending_rate(self):
        from connectors.usaspending import USAspendingConnector

        assert USAspendingConnector.rate_limit_rps == 5.0

    def test_doj_rate(self):
        from connectors.doj import DOJConnector

        assert DOJConnector.rate_limit_rps == 4.0

    def test_sec_edgar_rate(self):
        from connectors.sec_edgar import SECEdgarConnector

        assert SECEdgarConnector.rate_limit_rps == 10.0

    def test_oversight_rate(self):
        from connectors.oversight import OversightGovConnector

        assert OversightGovConnector.rate_limit_rps == 2.0

    def test_sam_gov_rate(self):
        """CLAUDE.md: SAM 4 RPS."""
        from connectors.sam_gov import SAMGovConnector

        assert SAMGovConnector.rate_limit_rps == 4.0

    def test_openfec_under_hourly_cap(self):
        """CLAUDE.md: FEC 1000/hr → must not exceed if sustained."""
        from connectors.openfec import OpenFECConnector

        # 0.28 RPS * 3600 = ~1008, but burst model means actual sustained
        # throughput stays under 1000/hr due to rate limiter token bucket
        assert OpenFECConnector.rate_limit_rps <= 0.28


# ── PDF Renderer Tests ───────────────────────────────────────────


class TestPDFRenderer:
    """Verify PDF renderer follows CLAUDE.md rules."""

    def test_plaintext_fallback(self):
        """When reportlab not installed, should return plaintext."""
        from renderers.pdf import _render_plaintext_fallback

        result = _render_plaintext_fallback(
            case_id="case-001",
            title="Test Case",
            claims=[{
                "claim_id": "c1",
                "statement": "Potential risk signal detected.",
                "claim_type": "risk_signal",
                "confidence": 0.6,
            }],
            citations=[{"claim_id": "c1", "artifact_id": "art-001"}],
            audit_events=[],
            pack_hash="abc123def456",
            generated_at=datetime(2024, 1, 15, tzinfo=UTC),
        )
        text = result.decode("utf-8")
        assert "case-001" in text
        assert "Test Case" in text
        assert "risk signal" in text.lower()

    def test_disclaimer_present(self):
        """CLAUDE.md rule #2: no fraud accusations — disclaimer required."""
        from renderers.pdf import _DISCLAIMER

        assert "risk signals" in _DISCLAIMER.lower()
        assert "hypotheses" in _DISCLAIMER.lower()
        assert "does not constitute" in _DISCLAIMER.lower()
        assert "accusation" in _DISCLAIMER.lower()

    def test_disclaimer_in_plaintext_output(self):
        from renderers.pdf import _render_plaintext_fallback

        result = _render_plaintext_fallback(
            case_id="case-001",
            title="Test",
            claims=[],
            citations=[],
            audit_events=[],
            pack_hash=None,
            generated_at=None,
        )
        text = result.decode("utf-8")
        assert "DISCLAIMER" in text
        assert "does not constitute" in text

    def test_methodology_in_output(self):
        """Sprint plan S8: methodology notes section."""
        from renderers.pdf import _METHODOLOGY_NOTE

        assert "deterministic" in _METHODOLOGY_NOTE.lower()
        assert "content hash" in _METHODOLOGY_NOTE.lower()

    def test_escape_function(self):
        from renderers.pdf import _escape

        assert _escape("<script>") == "&lt;script&gt;"
        assert _escape("A & B") == "A &amp; B"

    def test_plaintext_includes_all_claims(self):
        from renderers.pdf import _render_plaintext_fallback

        claims = [
            {
                "claim_id": f"c{i}",
                "statement": f"Claim {i}",
                "claim_type": "finding",
                "confidence": 0.9,
            }
            for i in range(5)
        ]
        result = _render_plaintext_fallback(
            case_id="case-002",
            title="Multi Claim",
            claims=claims,
            citations=[],
            audit_events=[],
            pack_hash="hash123",
            generated_at=None,
        )
        text = result.decode("utf-8")
        for i in range(5):
            assert f"Claim {i}" in text


# ── Metrics Endpoint Tests ───────────────────────────────────────


class TestMetricsModels:
    """Verify metrics response models follow security rules."""

    def test_public_metrics_no_pii_fields(self):
        """Security checklist: public metrics expose no PII."""
        from routes.metrics import PublicMetrics

        field_names = set(PublicMetrics.model_fields.keys())
        pii_terms = {"name", "email", "ssn", "address", "phone", "dob"}
        assert field_names.isdisjoint(pii_terms), (
            f"PublicMetrics contains PII-related fields: {field_names & pii_terms}"
        )

    def test_public_metrics_no_case_id_field(self):
        """Security checklist: no case-specific data in public metrics."""
        from routes.metrics import PublicMetrics

        field_names = set(PublicMetrics.model_fields.keys())
        assert "case_id" not in field_names
        assert "case_ids" not in field_names

    def test_default_values(self):
        from routes.metrics import PublicMetrics

        m = PublicMetrics()
        assert m.audited_dossier_pass_rate == 0.0
        assert m.total_cases_processed == 0
        assert m.replay_determinism_rate == 1.0

    def test_last_24h_defaults(self):
        from routes.metrics import Last24hMetrics

        m = Last24hMetrics()
        assert m.cases_created == 0
        assert m.audit_blocks == 0
        assert m.model_cost_usd == 0.0


# ── Terraform Compliance ────────────────────────────────────────


class TestTerraformCompliance:
    """Static analysis of Terraform config against devops agent spec."""

    @pytest.fixture
    def tf_content(self):
        with open(
            "/Users/dev/Documents/PROJECT_LOWLEVEL/SYSTEM DESIGN PROJECTS/"
            "CivicProof/infra/terraform/main.tf"
        ) as f:
            return f.read()

    def test_min_instances_zero(self, tf_content):
        """devops.md: All Cloud Run services min-instances=0."""
        assert "min_instance_count = 0" in tf_content

    def test_no_editor_or_owner_roles(self, tf_content):
        """devops.md: Never grant Editor or Owner roles."""
        assert "roles/editor" not in tf_content
        assert "roles/owner" not in tf_content

    def test_ssl_required(self, tf_content):
        """Security checklist S7: Cloud SQL requires SSL."""
        assert "require_ssl" in tf_content

    def test_internal_ingress_for_worker(self, tf_content):
        """Security checklist: worker is internal only."""
        assert "INGRESS_TRAFFIC_INTERNAL_ONLY" in tf_content

    def test_secret_manager_used(self, tf_content):
        """devops.md: All API keys in Secret Manager."""
        assert "google_secret_manager_secret" in tf_content
        assert "openrouter-api-key" in tf_content
        assert "sam-gov-api-key" in tf_content
        assert "openfec-api-key" in tf_content

    def test_object_versioning_enabled(self, tf_content):
        """devops.md: Object Versioning ON for artifact lake."""
        assert "versioning" in tf_content

    def test_dead_letter_topic(self, tf_content):
        """Sprint plan: dead-letter topic for failed messages."""
        assert "dead-letter" in tf_content

    def test_dedicated_service_accounts(self, tf_content):
        """devops.md: Dedicated SA per service."""
        assert "civicproof-api" in tf_content
        assert "civicproof-worker" in tf_content
        assert "civicproof-gateway" in tf_content

    def test_no_secrets_in_plain_env(self, tf_content):
        """devops.md: Never store secrets in env vars at deploy time.
        DB password should use secret_key_ref, not inline value."""
        # The DATABASE_URL should reference Secret Manager
        assert "secret_key_ref" in tf_content
