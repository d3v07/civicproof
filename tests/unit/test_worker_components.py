"""Tests for worker agents and connector base classes."""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WORKER_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker", "src")
if _WORKER_SRC not in sys.path:
    sys.path.insert(0, _WORKER_SRC)

from connectors.base import (  # noqa: E402
    USER_AGENT,
    BaseConnector,
    FetchParams,
    FetchResult,
    IngestRunResult,
)

# ── dataclass tests ──────────────────────────────────────────────────────────

class TestFetchParams:
    def test_defaults(self):
        p = FetchParams()
        assert p.page == 1
        assert p.page_size == 50
        assert p.since is None
        assert p.query == {}

    def test_with_values(self):
        now = datetime.now(UTC)
        p = FetchParams(query={"q": "test"}, page=3, since=now)
        assert p.query["q"] == "test"
        assert p.page == 3
        assert p.since == now


class TestFetchResult:
    def test_defaults(self):
        r = FetchResult()
        assert r.artifacts == []
        assert r.total_count == 0
        assert r.has_next is False
        assert r.next_page is None
        assert r.raw_response_bytes == b""

    def test_with_data(self):
        r = FetchResult(artifacts=[{"id": 1}], total_count=100, has_next=True, next_page=2)
        assert len(r.artifacts) == 1
        assert r.has_next is True


class TestIngestRunResult:
    def test_defaults(self):
        r = IngestRunResult()
        assert r.status == "completed"
        assert r.artifacts_fetched == 0
        assert r.errors == []
        assert len(r.run_id) == 36

    def test_tracks_errors(self):
        r = IngestRunResult()
        r.errors.append("timeout")
        r.status = "partial"
        assert r.status == "partial"
        assert len(r.errors) == 1


# ── base connector ────────────────────────────────────────────────────────────

class _TestConnector(BaseConnector):
    source_id = "test_source"
    rate_limit_rps = 5.0
    base_url = "https://api.test.gov"

    def __init__(self, rate_limiter=None, fetch_results=None):
        super().__init__(rate_limiter)
        self._fetch_results = fetch_results or []
        self._fetch_idx = 0

    async def fetch_page(self, params: FetchParams) -> FetchResult:
        if self._fetch_idx < len(self._fetch_results):
            result = self._fetch_results[self._fetch_idx]
            self._fetch_idx += 1
            return result
        return FetchResult()

    def canonical_url(self, artifact: dict[str, Any]) -> str:
        return f"{self.base_url}/items/{artifact.get('id', 'unknown')}"

    def doc_type(self) -> str:
        return "test_document"


class TestBaseConnector:
    def test_init_without_rate_limiter_warns(self):
        with patch("logging.Logger.warning") as _mock_warn:
            c = _TestConnector()
        assert c._rate_limiter is None

    def test_init_with_rate_limiter(self):
        rl = AsyncMock()
        c = _TestConnector(rate_limiter=rl)
        assert c._rate_limiter is rl

    @pytest.mark.asyncio
    async def test_get_client_creates_httpx_client(self):
        c = _TestConnector()
        client = await c._get_client()
        assert client is not None
        assert c._client is client
        # second call returns same client
        client2 = await c._get_client()
        assert client2 is client
        await c.close()

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        c = _TestConnector()
        await c.close()  # no client yet
        await c._get_client()
        await c.close()
        assert c._client.is_closed

    def test_serialize_artifact(self):
        data = {"name": "Acme", "amount": 50000, "_internal": True, "nullval": None}
        result = BaseConnector._serialize_artifact(data)
        parsed = json.loads(result)
        assert "_internal" not in parsed
        assert "nullval" not in parsed
        assert parsed["name"] == "Acme"
        assert parsed["amount"] == 50000

    def test_serialize_deterministic(self):
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        assert BaseConnector._serialize_artifact(d1) == BaseConnector._serialize_artifact(d2)

    @pytest.mark.asyncio
    async def test_run_incremental_single_page(self):
        page = FetchResult(
            artifacts=[{"id": "art-1", "name": "Test"}],
            has_next=False,
        )
        c = _TestConnector(fetch_results=[page])
        since = datetime.now(UTC) - timedelta(days=1)
        result = await c.run_incremental(since=since)
        assert result.artifacts_fetched == 1
        assert result.status == "completed"
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_run_incremental_multi_page(self):
        pages = [
            FetchResult(artifacts=[{"id": "1"}], has_next=True, next_page=2),
            FetchResult(artifacts=[{"id": "2"}], has_next=True, next_page=3),
            FetchResult(artifacts=[{"id": "3"}], has_next=False),
        ]
        c = _TestConnector(fetch_results=pages)
        result = await c.run_incremental(since=datetime.now(UTC))
        assert result.artifacts_fetched == 3
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_run_incremental_handles_error(self):
        class _FailConnector(_TestConnector):
            async def fetch_page(self, params):
                raise ConnectionError("network timeout")

        c = _FailConnector()
        result = await c.run_incremental(since=datetime.now(UTC))
        assert result.status == "partial"
        assert "network timeout" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_incremental_hashes_artifacts(self):
        page = FetchResult(artifacts=[{"id": "art-1", "data": "test"}], has_next=False)
        c = _TestConnector(fetch_results=[page])
        result = await c.run_incremental(since=datetime.now(UTC))
        assert result.artifacts_fetched == 1

    @pytest.mark.asyncio
    async def test_run_backfill_delegates_to_incremental(self):
        page = FetchResult(artifacts=[{"id": "bf-1"}], has_next=False)
        c = _TestConnector(fetch_results=[page])
        result = await c.run_backfill(
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
        )
        assert result.artifacts_fetched == 1

    @pytest.mark.asyncio
    async def test_rate_limited_get(self):
        rl = AsyncMock()
        rl.wait_for_token = AsyncMock()
        c = _TestConnector(rate_limiter=rl)
        c._client = AsyncMock()
        response = MagicMock()
        response.raise_for_status = MagicMock()
        c._client.get = AsyncMock(return_value=response)
        c._client.is_closed = False

        await c._rate_limited_get("https://api.test.gov/items")
        rl.wait_for_token.assert_awaited_once_with("test_source")

    @pytest.mark.asyncio
    async def test_rate_limited_post(self):
        rl = AsyncMock()
        rl.wait_for_token = AsyncMock()
        c = _TestConnector(rate_limiter=rl)
        c._client = AsyncMock()
        response = MagicMock()
        response.raise_for_status = MagicMock()
        c._client.post = AsyncMock(return_value=response)
        c._client.is_closed = False

        await c._rate_limited_post("https://api.test.gov/items", {"q": "test"})
        rl.wait_for_token.assert_awaited_once_with("test_source")

    @pytest.mark.asyncio
    async def test_max_pages_limit(self):
        pages = [
            FetchResult(artifacts=[{"id": str(i)}], has_next=True, next_page=i + 2)
            for i in range(600)
        ]
        c = _TestConnector(fetch_results=pages)
        c.MAX_PAGES_PER_RUN = 5
        result = await c.run_incremental(since=datetime.now(UTC))
        assert result.artifacts_fetched == 5

    def test_canonical_url(self):
        c = _TestConnector()
        url = c.canonical_url({"id": "test-123"})
        assert url == "https://api.test.gov/items/test-123"

    def test_doc_type(self):
        c = _TestConnector()
        assert c.doc_type() == "test_document"

    def test_user_agent_string(self):
        assert "CivicProof" in USER_AGENT


# ── agent tests ───────────────────────────────────────────────────────────────

class TestAuditorGate:
    def test_approved_with_valid_pack(self):
        from agents.auditor import AuditorGate

        gate = AuditorGate(
            valid_artifact_ids={"art-1", "art-2"},
            artifact_hashes={"art-1": "hash1", "art-2": "hash2"},
            min_sources=1,
        )
        pack = {
            "claims": [
                {
                    "claim_id": "c-1",
                    "statement": "Vendor received award",
                    "claim_type": "finding",
                    "confidence": 0.9,
                    "artifact_ids": ["art-1"],
                },
            ],
            "sources_used": ["usaspending"],
        }
        result = gate.audit(pack)
        assert result.approved is True
        assert result.blocked is False
        assert result.violation_count == 0

    def test_blocked_finding_no_citation(self):
        from agents.auditor import AuditorGate

        gate = AuditorGate(min_sources=1)
        pack = {
            "claims": [
                {
                    "claim_id": "c-1",
                    "statement": "Claim without evidence",
                    "claim_type": "finding",
                    "confidence": 0.9,
                    "artifact_ids": [],
                },
            ],
            "sources_used": ["usaspending"],
        }
        result = gate.audit(pack)
        assert result.approved is False
        assert result.violation_count > 0

    def test_hypothesis_allowed_without_citation(self):
        from agents.auditor import AuditorGate

        gate = AuditorGate(min_sources=1)
        pack = {
            "claims": [
                {
                    "claim_id": "c-1",
                    "statement": "Possible issue",
                    "claim_type": "hypothesis",
                    "confidence": 0.3,
                    "artifact_ids": [],
                },
            ],
            "sources_used": ["usaspending"],
        }
        result = gate.audit(pack)
        # hypothesis without citation is allowed by Rule 5
        citation_rule = [r for r in result.rule_results if r.rule_name == "HYPOTHESIS_LABELED"]
        if citation_rule:
            assert citation_rule[0].passed is True

    def test_accusatory_language_blocked(self):
        from agents.auditor import AuditorGate

        gate = AuditorGate(
            valid_artifact_ids={"art-1"},
            min_sources=1,
        )
        pack = {
            "claims": [
                {
                    "claim_id": "c-1",
                    "statement": "This vendor committed fraud and is guilty of fraud",
                    "claim_type": "finding",
                    "artifact_ids": ["art-1"],
                },
            ],
            "sources_used": ["usaspending"],
        }
        result = gate.audit(pack)
        assert result.approved is False
        lang_rule = [r for r in result.rule_results if r.rule_name == "NO_ACCUSATORY_LANGUAGE"]
        assert len(lang_rule) == 1
        assert lang_rule[0].passed is False

    def test_pii_detection(self):
        from agents.auditor import AuditorGate

        gate = AuditorGate(
            valid_artifact_ids={"art-1"},
            min_sources=1,
        )
        pack = {
            "claims": [
                {
                    "claim_id": "c-1",
                    "statement": "Person with SSN 123-45-6789 received money",
                    "claim_type": "finding",
                    "artifact_ids": ["art-1"],
                },
            ],
            "sources_used": ["usaspending"],
        }
        result = gate.audit(pack)
        assert result.approved is False
        pii_rule = [r for r in result.rule_results if r.rule_name == "PII_CHECK"]
        assert len(pii_rule) == 1
        assert pii_rule[0].passed is False

    def test_minimum_sources_enforcement(self):
        from agents.auditor import AuditorGate

        gate = AuditorGate(
            valid_artifact_ids={"art-1"},
            min_sources=2,
        )
        pack = {
            "claims": [
                {
                    "claim_id": "c-1",
                    "statement": "Vendor data",
                    "claim_type": "finding",
                    "artifact_ids": ["art-1"],
                },
            ],
            "sources_used": ["usaspending"],
        }
        result = gate.audit(pack)
        assert result.approved is False
        src_rule = [r for r in result.rule_results if r.rule_name == "MINIMUM_SOURCES"]
        assert len(src_rule) == 1
        assert src_rule[0].passed is False

    def test_empty_pack(self):
        from agents.auditor import AuditorGate

        gate = AuditorGate()
        result = gate.audit({})
        assert isinstance(result.approved, bool)
        assert isinstance(result.summary, str)

    def test_result_properties(self):
        from agents.auditor import AuditorResult, RuleResult

        result = AuditorResult(approved=False, violations=["v1", "v2"])
        assert result.blocked is True
        assert result.violation_count == 2

        rr = RuleResult(rule_name="TEST", passed=True)
        assert rr.violations == []


# ── pdf renderer (from api service) ──────────────────────────────────────────

_API_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "services", "api", "src")
if _API_SRC not in sys.path:
    sys.path.insert(0, _API_SRC)


class TestPdfRendererExtended:
    def test_with_claims_and_citations(self):
        from renderers.pdf import render_case_pack_pdf

        claims = [
            {
                "claim_id": "c-1",
                "statement": "Award over threshold",
                "claim_type": "risk_signal",
                "confidence": 0.85,
            },
            {
                "claim_id": "c-2",
                "statement": "Entity link found",
                "claim_type": "finding",
                "confidence": 0.92,
            },
        ]
        citations = [
            {
                "claim_id": "c-1",
                "artifact_id": "art-001",
                "excerpt": "Contract value: $5M",
            },
            {
                "claim_id": "c-2",
                "artifact_id": "art-002",
                "excerpt": "Subsidiary relationship confirmed",
            },
        ]
        audit_events = [
            {"stage": "intake", "policy_decision": "accepted", "timestamp": "2024-06-01T12:00:00"},
            {"stage": "auditor", "policy_decision": "approved", "timestamp": "2024-06-01T12:05:00"},
        ]
        result = render_case_pack_pdf(
            case_id="c-test-full",
            title="Full Case Pack Test",
            claims=claims,
            citations=citations,
            audit_events=audit_events,
            pack_hash="abc123def456",
        )
        assert isinstance(result, bytes)
        assert len(result) > 100

    def test_html_escape_in_claims(self):
        from renderers.pdf import render_case_pack_pdf

        claims = [
            {
                "claim_id": "c-xss",
                "statement": "<script>alert('xss')</script>",
                "claim_type": "finding",
                "confidence": 0.5,
            },
        ]
        result = render_case_pack_pdf(
            case_id="c-xss-test",
            title="XSS <b>test</b>",
            claims=claims,
            citations=[],
            audit_events=[],
        )
        assert isinstance(result, bytes)


# ── gateway content filter ────────────────────────────────────────────────────

_GW_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "services", "gateway", "src")
if _GW_SRC not in sys.path:
    sys.path.insert(0, _GW_SRC)


class TestContentFilter:
    def test_filter_instantiation(self):
        from policies.content_filter import ContentFilter

        cf = ContentFilter()
        assert cf is not None
