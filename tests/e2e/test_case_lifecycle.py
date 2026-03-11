"""E2E tests: Full case lifecycle through API endpoints.

Tests the complete HTTP request/response cycle using FastAPI's TestClient.
DB and Redis are mocked, but all middleware, routing, serialization, and
response formatting are exercised end-to-end.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from civicproof_common.db.models import (
    AuditEventModel,
    CaseModel,
    CasePackModel,
    CitationModel,
    ClaimModel,
)
from civicproof_common.db.session import get_session
from httpx import ASGITransport, AsyncClient

# ── Fixtures ────────────────────────────────────────────────────────────


def _make_case(
    case_id: str | None = None,
    status: str = "pending",
    title: str = "Test Investigation",
    seed_input: dict | None = None,
) -> MagicMock:
    case = MagicMock(spec=CaseModel)
    case.case_id = case_id or str(uuid.uuid4())
    case.title = title
    case.status = status
    case.seed_input = seed_input or {"vendor_name": "Acme Corp"}
    case.created_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    case.updated_at = datetime(2026, 1, 15, 10, 0, 1, tzinfo=UTC)
    case.claims = []
    case.audit_events = []
    case.case_packs = []
    return case


def _make_complete_case(case_id: str | None = None) -> MagicMock:
    """Case with claims, citations, audit events, and a case pack."""
    cid = case_id or str(uuid.uuid4())
    case = _make_case(case_id=cid, status="complete")

    cit = MagicMock(spec=CitationModel)
    cit.citation_id = str(uuid.uuid4())
    cit.claim_id = "cl-1"
    cit.artifact_id = "art-001"
    cit.excerpt = "Received $5M in sole-source contracts"
    cit.page_ref = "p.12"

    claim = MagicMock(spec=ClaimModel)
    claim.claim_id = "cl-1"
    claim.statement = "Entity received $5M in sole-source contracts."
    claim.claim_type = "finding"
    claim.confidence = 0.95
    claim.is_audited = True
    claim.audit_passed = True
    claim.citations = [cit]

    audit = MagicMock(spec=AuditEventModel)
    audit.audit_event_id = str(uuid.uuid4())
    audit.stage = "auditor_gate"
    audit.policy_decision = "approved"
    audit.detail = "All rules passed"
    audit.timestamp = datetime(2026, 1, 15, 10, 5, 0, tzinfo=UTC)

    pack = MagicMock(spec=CasePackModel)
    pack.pack_id = str(uuid.uuid4())
    pack.case_id = cid
    pack.pack_hash = "abc123def456"
    pack.generated_at = datetime(2026, 1, 15, 10, 5, 0, tzinfo=UTC)

    case.claims = [claim]
    case.audit_events = [audit]
    case.case_packs = [pack]
    return case


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.DATABASE_URL = "sqlite+aiosqlite://"
    s.REDIS_URL = "redis://localhost:6379/0"
    s.DEBUG = True
    s.LOG_LEVEL = "INFO"
    s.API_RATE_LIMIT_PER_MINUTE = 1000
    s.API_SECRET_KEY = "test-secret"
    s.OTEL_EXPORTER_OTLP_ENDPOINT = ""
    return s


@pytest.fixture
def app(mock_settings):
    with patch("civicproof_common.config.get_settings", return_value=mock_settings):
        from services.api.src.main import create_app
        return create_app()


def _override_db(mock_db):
    """Create a dependency override for get_session."""
    async def _get_mock_session():
        yield mock_db
    return _get_mock_session


# ── Test Cases ──────────────────────────────────────────────────────────


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, app, mock_settings):
        with patch("civicproof_common.config.get_settings", return_value=mock_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestListCases:
    @pytest.mark.asyncio
    async def test_list_cases_empty(self, app, mock_settings):
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, rows_result])

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/v1/cases")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_cases_with_results(self, app, mock_settings):
        cases = [_make_case(status="complete"), _make_case(status="pending")]
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 2
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = cases
        mock_db.execute = AsyncMock(side_effect=[count_result, rows_result])

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/v1/cases")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["status"] == "complete"

    @pytest.mark.asyncio
    async def test_list_cases_pagination(self, app, mock_settings):
        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 100
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [_make_case()]
        mock_db.execute = AsyncMock(side_effect=[count_result, rows_result])

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/v1/cases?page=3&page_size=10")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 100
        assert data["page"] == 3
        assert data["page_size"] == 10


class TestCreateCase:
    @pytest.mark.asyncio
    async def test_create_case_success(self, app, mock_settings):
        new_case = _make_case(status="pending")

        mock_db = AsyncMock()
        dedup_result = MagicMock()
        dedup_result.scalars.return_value = iter([])
        mock_db.execute = AsyncMock(return_value=dedup_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        async def _refresh(obj):
            obj.case_id = new_case.case_id
            obj.title = "Test Investigation"
            obj.status = "pending"
            obj.seed_input = {"vendor_name": "Acme Corp"}
            obj.created_at = new_case.created_at
            obj.updated_at = new_case.updated_at

        mock_db.refresh = AsyncMock(side_effect=_refresh)

        mock_redis = AsyncMock()
        mock_redis.rpush = AsyncMock(return_value=1)
        mock_redis.aclose = AsyncMock()

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with (
                patch("civicproof_common.config.get_settings", return_value=mock_settings),
                patch("redis.asyncio.from_url", return_value=mock_redis),
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post("/v1/cases", json={
                        "title": "Test Investigation",
                        "seed_input": {"vendor_name": "Acme Corp"},
                    })
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Investigation"
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_case_missing_title(self, app, mock_settings):
        with patch("civicproof_common.config.get_settings", return_value=mock_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/v1/cases", json={
                    "seed_input": {"vendor_name": "Test"},
                })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_case_empty_title(self, app, mock_settings):
        with patch("civicproof_common.config.get_settings", return_value=mock_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/v1/cases", json={
                    "title": "",
                    "seed_input": {"vendor_name": "Test"},
                })
        assert resp.status_code == 422


class TestGetCase:
    @pytest.mark.asyncio
    async def test_get_case_found(self, app, mock_settings):
        case = _make_case()
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = case
        mock_db.execute = AsyncMock(return_value=result)

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/v1/cases/{case.case_id}")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["case_id"] == case.case_id
        assert data["title"] == "Test Investigation"

    @pytest.mark.asyncio
    async def test_get_case_not_found(self, app, mock_settings):
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/v1/cases/nonexistent-id")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"] == "case_not_found"


class TestGetCasePack:
    @pytest.mark.asyncio
    async def test_get_pack_complete_case(self, app, mock_settings):
        case = _make_complete_case()
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = case
        mock_db.execute = AsyncMock(return_value=result)

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/v1/cases/{case.case_id}/pack")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["case_id"] == case.case_id
        assert len(data["claims"]) == 1
        assert data["claims"][0]["statement"] == "Entity received $5M in sole-source contracts."
        assert len(data["citations"]) == 1
        assert data["citations"][0]["artifact_id"] == "art-001"
        assert len(data["audit_events"]) == 1
        assert data["pack_hash"] == "abc123def456"

    @pytest.mark.asyncio
    async def test_get_pack_pending_case_returns_409(self, app, mock_settings):
        case = _make_case(status="pending")
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = case
        mock_db.execute = AsyncMock(return_value=result)

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/v1/cases/{case.case_id}/pack")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 409
        data = resp.json()
        assert data["detail"]["error"] == "pack_not_ready"

    @pytest.mark.asyncio
    async def test_get_pack_not_found(self, app, mock_settings):
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/v1/cases/missing-id/pack")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_returns_aggregates(self, app, mock_settings):
        mock_db = AsyncMock()
        call_results = []
        # 1: total_cases
        r = MagicMock()
        r.scalar.return_value = 42
        call_results.append(r)
        # 2: total_artifacts
        r = MagicMock()
        r.scalar.return_value = 200
        call_results.append(r)
        # 3: sources_active
        r = MagicMock()
        r.scalar.return_value = 4
        call_results.append(r)
        # 4: total_packs
        r = MagicMock()
        r.scalar.return_value = 30
        call_results.append(r)
        # 5: passed_packs
        r = MagicMock()
        r.scalar.return_value = 28
        call_results.append(r)
        # 6: cases_24h
        r = MagicMock()
        r.scalar.return_value = 5
        call_results.append(r)
        # 7: artifacts_24h
        r = MagicMock()
        r.scalar.return_value = 15
        call_results.append(r)
        # 8: blocks_24h
        r = MagicMock()
        r.scalar.return_value = 1
        call_results.append(r)
        # 9: total_audits
        r = MagicMock()
        r.scalar.return_value = 100
        call_results.append(r)
        # 10: total_blocks
        r = MagicMock()
        r.scalar.return_value = 5
        call_results.append(r)
        # 11: timing_query
        r = MagicMock()
        r.all.return_value = [(10.0,), (15.0,), (20.0,)]
        call_results.append(r)
        # 12: total_mentions
        r = MagicMock()
        r.scalar.return_value = 50
        call_results.append(r)
        # 13: resolved_mentions
        r = MagicMock()
        r.scalar.return_value = 45
        call_results.append(r)

        mock_db.execute = AsyncMock(side_effect=call_results)

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/v1/metrics/public")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cases_processed"] == 42
        assert data["total_artifacts_ingested"] == 200
        assert data["sources_active"] == 4
        assert data["audited_dossier_pass_rate"] > 0
        assert data["hallucination_caught_rate"] == 0.05
        assert data["median_tip_to_dossier_seconds"] == 15.0
        assert data["entity_resolution_coverage"] == 0.9
        assert data["last_24h"]["cases_created"] == 5
        assert data["last_24h"]["artifacts_fetched"] == 15
        assert data["last_24h"]["audit_blocks"] == 1


class TestCasePackPDF:
    @pytest.mark.asyncio
    async def test_pdf_returns_bytes(self, app, mock_settings):
        case = _make_complete_case()
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = case
        mock_db.execute = AsyncMock(return_value=result)

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with (
                patch("civicproof_common.config.get_settings", return_value=mock_settings),
                patch("services.api.src.routes.cases._render_pdf", return_value=b"%PDF-1.4 fake"),
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/v1/cases/{case.case_id}/pack.pdf")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert b"%PDF" in resp.content

    @pytest.mark.asyncio
    async def test_pdf_pending_case_returns_409(self, app, mock_settings):
        case = _make_case(status="ingesting")
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = case
        mock_db.execute = AsyncMock(return_value=result)

        app.dependency_overrides[get_session] = _override_db(mock_db)
        try:
            with patch("civicproof_common.config.get_settings", return_value=mock_settings):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/v1/cases/{case.case_id}/pack.pdf")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 409
