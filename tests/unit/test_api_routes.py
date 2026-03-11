"""API route tests — covers cases, search, metrics, ingest, health, and PDF endpoints."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure service src is importable
_API_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "services", "api", "src")
if _API_SRC not in sys.path:
    sys.path.insert(0, _API_SRC)

from civicproof_common.db.session import get_session  # noqa: E402
from civicproof_common.schemas.cases import CaseStatus  # noqa: E402
from routes import cases as cases_router_mod  # noqa: E402
from routes import health as health_router_mod  # noqa: E402
from routes import ingest as ingest_router_mod  # noqa: E402
from routes import metrics as metrics_router_mod  # noqa: E402
from routes import search as search_router_mod  # noqa: E402

# ── helpers ──────────────────────────────────────────────────────────────────

def _scalar_result(value: Any) -> MagicMock:
    r = MagicMock()
    r.scalar.return_value = value
    r.scalar_one_or_none.return_value = value
    r.all.return_value = []
    scalars = MagicMock()
    scalars.all.return_value = []
    r.scalars.return_value = scalars
    return r


def _scalars_all_result(values: list) -> MagicMock:
    r = MagicMock()
    r.scalar.return_value = len(values)
    r.scalar_one_or_none.return_value = values[0] if values else None
    scalars = MagicMock()
    scalars.all.return_value = values
    scalars.__iter__ = MagicMock(return_value=iter(values))
    r.scalars.return_value = scalars
    r.all.return_value = values
    return r


def _make_case_model(
    case_id: str | None = None,
    status: str = CaseStatus.PENDING.value,
    title: str = "Test Case",
) -> MagicMock:
    now = datetime.now(UTC)
    m = MagicMock()
    m.case_id = case_id or str(uuid.uuid4())
    m.title = title
    m.status = status
    m.seed_input = {"vendor_name": "Acme Corp"}
    m.created_at = now
    m.updated_at = now
    m.claims = []
    m.audit_events = []
    m.case_packs = []
    return m


def _make_entity_model() -> MagicMock:
    m = MagicMock()
    m.entity_id = str(uuid.uuid4())
    m.entity_type = "vendor"
    m.canonical_name = "Acme Solutions LLC"
    m.uei = "ABCDEF123456"
    m.cage_code = "1AB2C"
    m.aliases = ["Acme LLC"]
    return m


def _make_artifact_model() -> MagicMock:
    m = MagicMock()
    m.artifact_id = str(uuid.uuid4())
    m.source = "usaspending"
    m.source_url = "https://api.usaspending.gov/awards/123"
    m.content_hash = "a" * 64
    m.retrieved_at = datetime.now(UTC)
    m.metadata_ = {"fiscal_year": "2024"}
    return m


def _make_datasource_model() -> MagicMock:
    m = MagicMock()
    m.source_id = str(uuid.uuid4())
    m.name = "usaspending"
    m.is_active = True
    return m


def _make_ingestrun_model(source_id: str) -> MagicMock:
    m = MagicMock()
    m.run_id = str(uuid.uuid4())
    m.source_id = source_id
    m.status = "pending"
    m.parameters = {}
    m.started_at = datetime.now(UTC)
    return m


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _build_app(mock_db: AsyncMock, *routers) -> FastAPI:
    app = FastAPI()

    async def _override_session():
        yield mock_db

    app.dependency_overrides[get_session] = _override_session
    for router in routers:
        app.include_router(router)
    return app


# ── health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_liveness(self, mock_db):
        app = _build_app(mock_db, health_router_mod.router)
        with TestClient(app) as client:
            r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_readiness_no_redis(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(1))
        app = _build_app(mock_db, health_router_mod.router)
        # No app.state.redis — returns 503 because "not_configured" != "ok"
        with TestClient(app) as client:
            r = client.get("/ready")
        assert r.status_code == 503
        data = r.json()
        assert data["detail"]["checks"]["postgres"] == "ok"
        assert data["detail"]["checks"]["redis"] == "not_configured"

    def test_readiness_postgres_error(self, mock_db):
        mock_db.execute = AsyncMock(side_effect=Exception("connection refused"))
        app = _build_app(mock_db, health_router_mod.router)
        with TestClient(app) as client:
            r = client.get("/ready")
        assert r.status_code == 503
        assert r.json()["detail"]["checks"]["postgres"] == "error"


# ── cases ─────────────────────────────────────────────────────────────────────

class TestListCases:
    def test_empty_list(self, mock_db):
        mock_db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_all_result([]),
        ])
        app = _build_app(mock_db, cases_router_mod.router)
        app.include_router(cases_router_mod.router, prefix="/v1")
        with TestClient(app) as client:
            r = client.get("/v1/cases")
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_with_items(self, mock_db):
        case = _make_case_model()
        mock_db.execute = AsyncMock(side_effect=[
            _scalar_result(1),
            _scalars_all_result([case]),
        ])
        app = _build_app(mock_db)
        app.include_router(cases_router_mod.router, prefix="/v1")

        async def _override_session():
            yield mock_db
        app.dependency_overrides[get_session] = _override_session

        with TestClient(app) as client:
            r = client.get("/v1/cases")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["case_id"] == case.case_id

    def test_status_filter(self, mock_db):
        mock_db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_all_result([]),
        ])
        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get("/v1/cases?status=complete")
        assert r.status_code == 200

    def test_pagination_params(self, mock_db):
        mock_db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_all_result([]),
        ])
        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get("/v1/cases?page=2&page_size=10")
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 2
        assert body["page_size"] == 10


class TestCreateCase:
    def _app_with_no_existing(self, mock_db):
        # existing cases check (scalars→empty), then flush via add+flush
        existing_result = _scalars_all_result([])
        mock_db.execute = AsyncMock(return_value=existing_result)

        case_id = str(uuid.uuid4())

        async def refresh_side_effect(obj):
            obj.case_id = case_id
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=refresh_side_effect)

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")
        return app, case_id

    def test_create_success(self, mock_db):
        app, _ = self._app_with_no_existing(mock_db)
        with TestClient(app) as client:
            r = client.post("/v1/cases", json={
                "title": "Test Investigation",
                "seed_input": {"vendor_name": "Acme Corp"},
            })
        assert r.status_code == 201
        body = r.json()
        assert body["title"] == "Test Investigation"
        assert body["status"] == CaseStatus.PENDING.value

    def test_missing_title_rejected(self, mock_db):
        app, _ = self._app_with_no_existing(mock_db)
        with TestClient(app) as client:
            r = client.post("/v1/cases", json={"seed_input": {"vendor_name": "Acme"}})
        assert r.status_code == 422

    def test_empty_title_rejected(self, mock_db):
        app, _ = self._app_with_no_existing(mock_db)
        with TestClient(app) as client:
            r = client.post("/v1/cases", json={"title": "", "seed_input": {}})
        assert r.status_code == 422

    def test_idempotency_returns_existing(self, mock_db):
        existing = _make_case_model(title="Dup Case")
        existing.seed_input = {"vendor_name": "Acme Corp"}
        existing_result = _scalars_all_result([existing])
        mock_db.execute = AsyncMock(return_value=existing_result)

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.post("/v1/cases", json={
                "title": "Dup Case",
                "seed_input": {"vendor_name": "Acme Corp"},
            })
        assert r.status_code == 201
        assert r.json()["title"] == "Dup Case"
        mock_db.commit.assert_not_called()


class TestGetCase:
    def test_found(self, mock_db):
        case = _make_case_model()
        mock_db.execute = AsyncMock(return_value=_scalar_result(case))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get(f"/v1/cases/{case.case_id}")
        assert r.status_code == 200
        assert r.json()["case_id"] == case.case_id

    def test_not_found(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(None))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get("/v1/cases/nonexistent-id")
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "case_not_found"


class TestGetCasePack:
    def _make_complete_case(self) -> MagicMock:
        case = _make_case_model(status=CaseStatus.COMPLETE.value)
        case.claims = []
        case.audit_events = []
        case.case_packs = []
        return case

    def test_pack_not_ready(self, mock_db):
        case = _make_case_model(status=CaseStatus.PENDING.value)
        case.claims = []
        case.audit_events = []
        case.case_packs = []
        mock_db.execute = AsyncMock(return_value=_scalar_result(case))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get(f"/v1/cases/{case.case_id}/pack")
        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "pack_not_ready"

    def test_pack_complete(self, mock_db):
        case = self._make_complete_case()
        mock_db.execute = AsyncMock(return_value=_scalar_result(case))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get(f"/v1/cases/{case.case_id}/pack")
        assert r.status_code == 200
        body = r.json()
        assert body["case_id"] == case.case_id
        assert "claims" in body
        assert "citations" in body
        assert "audit_events" in body

    def test_pack_not_found(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(None))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get("/v1/cases/missing/pack")
        assert r.status_code == 404

    def test_pack_auditing_status_also_works(self, mock_db):
        case = _make_case_model(status=CaseStatus.AUDITING.value)
        case.claims = []
        case.audit_events = []
        case.case_packs = []
        mock_db.execute = AsyncMock(return_value=_scalar_result(case))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get(f"/v1/cases/{case.case_id}/pack")
        assert r.status_code == 200


class TestGetCasePackPdf:
    def test_pdf_returns_bytes(self, mock_db):
        case = _make_case_model(status=CaseStatus.COMPLETE.value)
        case.claims = []
        case.audit_events = []
        case.case_packs = []
        mock_db.execute = AsyncMock(return_value=_scalar_result(case))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get(f"/v1/cases/{case.case_id}/pack.pdf")
        assert r.status_code == 200
        assert "pdf" in r.headers["content-type"] or len(r.content) > 0
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_pdf_not_found(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(None))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get("/v1/cases/missing/pack.pdf")
        assert r.status_code == 404

    def test_pdf_not_ready(self, mock_db):
        case = _make_case_model(status=CaseStatus.PENDING.value)
        case.claims = []
        case.audit_events = []
        case.case_packs = []
        mock_db.execute = AsyncMock(return_value=_scalar_result(case))

        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(cases_router_mod.router, prefix="/v1")

        with TestClient(app) as client:
            r = client.get(f"/v1/cases/{case.case_id}/pack.pdf")
        assert r.status_code == 409


# ── search ────────────────────────────────────────────────────────────────────

class TestSearchEntities:
    def _app(self, mock_db):
        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(search_router_mod.router, prefix="/v1")
        return app

    def test_missing_query_rejected(self, mock_db):
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.get("/v1/search/entities")
        assert r.status_code == 422

    def test_empty_results(self, mock_db):
        mock_db.execute = AsyncMock(side_effect=[
            _scalars_all_result([]),
            _scalars_all_result([]),
        ])
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.get("/v1/search/entities?q=nobody")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_returns_entities(self, mock_db):
        entity = _make_entity_model()
        mock_db.execute = AsyncMock(side_effect=[
            _scalars_all_result([entity]),
            _scalars_all_result([entity]),
        ])
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.get("/v1/search/entities?q=acme")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["canonical_name"] == "Acme Solutions LLC"

    def test_entity_type_filter(self, mock_db):
        mock_db.execute = AsyncMock(side_effect=[
            _scalars_all_result([]),
            _scalars_all_result([]),
        ])
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.get("/v1/search/entities?q=test&entity_type=vendor")
        assert r.status_code == 200


class TestSearchArtifacts:
    def _app(self, mock_db):
        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(search_router_mod.router, prefix="/v1")
        return app

    def test_missing_query_rejected(self, mock_db):
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.get("/v1/search/artifacts")
        assert r.status_code == 422

    def test_returns_artifacts(self, mock_db):
        artifact = _make_artifact_model()
        mock_db.execute = AsyncMock(side_effect=[
            _scalars_all_result([artifact]),
            _scalars_all_result([artifact]),
        ])
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.get("/v1/search/artifacts?q=usaspending")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["source"] == "usaspending"


# ── metrics ───────────────────────────────────────────────────────────────────

class TestPublicMetrics:
    def _app(self, mock_db):
        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(metrics_router_mod.router, prefix="/v1")
        return app

    def test_returns_metrics_shape(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(0))
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.get("/v1/metrics/public")
        assert r.status_code == 200
        body = r.json()
        assert "audited_dossier_pass_rate" in body
        assert "total_cases_processed" in body
        assert "total_artifacts_ingested" in body
        assert "sources_active" in body
        assert "last_24h" in body

    def test_metrics_with_data(self, mock_db):
        timing_result = MagicMock()
        timing_result.scalar.return_value = None
        timing_result.all.return_value = [(12.5,), (15.0,), (18.3,)]

        mock_db.execute = AsyncMock(side_effect=[
            _scalar_result(47),   # total cases
            _scalar_result(1200), # total artifacts
            _scalar_result(6),    # sources
            _scalar_result(40),   # total packs
            _scalar_result(37),   # passed packs
            _scalar_result(3),    # cases 24h
            _scalar_result(892),  # artifacts 24h
            _scalar_result(1),    # blocks 24h
            _scalar_result(100),  # total audits
            _scalar_result(5),    # total blocks (hallucination)
            timing_result,        # timing query
            _scalar_result(500),  # total mentions
            _scalar_result(450),  # resolved mentions
        ])
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.get("/v1/metrics/public")
        assert r.status_code == 200
        body = r.json()
        assert body["total_cases_processed"] == 47
        assert body["sources_active"] == 6
        assert body["last_24h"]["cases_created"] == 3
        assert body["hallucination_caught_rate"] == 0.05
        assert body["median_tip_to_dossier_seconds"] == 15.0
        assert body["entity_resolution_coverage"] == 0.9


# ── ingest ────────────────────────────────────────────────────────────────────

class TestIngestRun:
    def _app(self, mock_db):
        app = FastAPI()

        async def _override():
            yield mock_db
        app.dependency_overrides[get_session] = _override
        app.include_router(ingest_router_mod.router, prefix="/v1")
        return app

    def test_source_not_found(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(None))
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.post("/v1/ingest/runs", json={"source_name": "nonexistent"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "data_source_not_found"

    def test_trigger_success(self, mock_db):
        ds = _make_datasource_model()
        mock_db.execute = AsyncMock(return_value=_scalar_result(ds))
        run = _make_ingestrun_model(ds.source_id)

        async def refresh_side_effect(obj):
            obj.run_id = run.run_id
            obj.source_id = run.source_id
            obj.status = run.status
            obj.parameters = run.parameters
            obj.started_at = run.started_at

        mock_db.refresh = AsyncMock(side_effect=refresh_side_effect)
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.post("/v1/ingest/runs", json={"source_name": "usaspending"})
        assert r.status_code == 202
        body = r.json()
        assert body["source_name"] == "usaspending"
        assert body["status"] == "pending"

    def test_missing_source_name_rejected(self, mock_db):
        app = self._app(mock_db)
        with TestClient(app) as client:
            r = client.post("/v1/ingest/runs", json={})
        assert r.status_code == 422


# ── pdf renderer unit ─────────────────────────────────────────────────────────

class TestPdfRenderer:
    def test_plaintext_fallback(self):
        from renderers.pdf import _render_plaintext_fallback

        result = _render_plaintext_fallback(
            case_id="c-001",
            title="Test Case",
            claims=[{
                "claim_type": "finding", "confidence": 0.9,
                "statement": "Test claim", "claim_id": "cl-001",
            }],
            citations=[{
                "claim_id": "cl-001",
                "artifact_id": "art-001",
                "excerpt": "Some text",
            }],
            audit_events=[],
            pack_hash="abc123",
            generated_at=None,
        )
        assert isinstance(result, bytes)
        assert b"Test Case" in result
        assert b"DISCLAIMER" in result
        assert b"FINDING" in result

    def test_render_returns_bytes(self):
        from renderers.pdf import render_case_pack_pdf

        result = render_case_pack_pdf(
            case_id="c-001",
            title="Test Case",
            claims=[],
            citations=[],
            audit_events=[],
        )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_escape_html_entities(self):
        from renderers.pdf import _escape

        assert _escape("a & b < c > d") == "a &amp; b &lt; c &gt; d"
        assert _escape("no special chars") == "no special chars"
