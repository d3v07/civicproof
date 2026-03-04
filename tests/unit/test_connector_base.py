"""Unit tests for BaseConnector and USAspendingConnector."""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from src.connectors.base import BaseConnector, FetchParams, FetchResult, IngestRunResult
from src.connectors.usaspending import USAspendingConnector


class TestFetchParams:
    def test_defaults(self):
        p = FetchParams()
        assert p.page == 1
        assert p.page_size == 50
        assert p.query == {}
        assert p.since is None

    def test_custom_values(self):
        p = FetchParams(query={"q": "test"}, page=3, page_size=25)
        assert p.query["q"] == "test"
        assert p.page == 3


class TestFetchResult:
    def test_defaults(self):
        r = FetchResult()
        assert r.artifacts == []
        assert r.total_count == 0
        assert r.has_next is False

    def test_with_data(self):
        r = FetchResult(artifacts=[{"a": 1}], total_count=100, has_next=True, next_page=2)
        assert len(r.artifacts) == 1
        assert r.next_page == 2


class TestIngestRunResult:
    def test_defaults(self):
        r = IngestRunResult()
        assert r.status == "completed"
        assert r.artifacts_fetched == 0
        assert len(r.run_id) > 0

    def test_error_tracking(self):
        r = IngestRunResult()
        r.errors.append("timeout")
        r.status = "partial"
        assert len(r.errors) == 1


class TestSerializeArtifact:
    def test_removes_underscore_keys(self):
        artifact = {"name": "test", "_internal": "skip", "amount": 100}
        raw = BaseConnector._serialize_artifact(artifact)
        parsed = json.loads(raw)
        assert "_internal" not in parsed
        assert "name" in parsed

    def test_removes_none_values(self):
        artifact = {"name": "test", "empty": None}
        raw = BaseConnector._serialize_artifact(artifact)
        parsed = json.loads(raw)
        assert "empty" not in parsed

    def test_deterministic(self):
        artifact = {"b": 2, "a": 1}
        r1 = BaseConnector._serialize_artifact(artifact)
        r2 = BaseConnector._serialize_artifact(artifact)
        assert r1 == r2


class TestUSAspendingConnector:
    def test_source_id(self):
        c = USAspendingConnector()
        assert c.source_id == "usaspending"

    def test_canonical_url(self):
        c = USAspendingConnector()
        url = c.canonical_url({"award_id": "CONT00123"})
        assert "CONT00123" in url
        assert "usaspending.gov" in url

    def test_canonical_url_fallback(self):
        c = USAspendingConnector()
        url = c.canonical_url({"generated_internal_id": "gen123"})
        assert "gen123" in url

    def test_doc_type(self):
        c = USAspendingConnector()
        assert c.doc_type() == "contract_award"

    def test_award_fields(self):
        c = USAspendingConnector()
        assert "Award ID" in c.AWARD_FIELDS
        assert "Recipient Name" in c.AWARD_FIELDS
        assert "Award Amount" in c.AWARD_FIELDS

    @pytest.mark.asyncio
    async def test_fetch_page_parses_response(self):
        c = USAspendingConnector()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "Award ID": "CONT001",
                    "Recipient Name": "ACME CORP",
                    "Award Amount": 50000,
                    "Awarding Agency": "DOD",
                    "Award Type": "Contract",
                    "Start Date": "2025-01-01",
                    "End Date": "2025-12-31",
                    "Recipient UEI": "ABC123",
                    "Extent Competed": "FULL AND OPEN",
                    "NAICS Code": "541519",
                }
            ],
            "page_metadata": {"total": 1, "hasNext": False},
        }
        mock_response.content = b"{}"

        with patch.object(c, "_rate_limited_post", new_callable=AsyncMock, return_value=mock_response):
            result = await c.fetch_page(FetchParams(
                query={"recipient_search_text": ["ACME"]},
            ))

        assert len(result.artifacts) == 1
        assert result.artifacts[0]["award_id"] == "CONT001"
        assert result.artifacts[0]["recipient_name"] == "ACME CORP"
        assert result.total_count == 1
        assert result.has_next is False

    @pytest.mark.asyncio
    async def test_fetch_page_with_pagination(self):
        c = USAspendingConnector()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"Award ID": "A1", "Recipient Name": "X"}],
            "page_metadata": {"total": 100, "hasNext": True},
        }
        mock_response.content = b"{}"

        with patch.object(c, "_rate_limited_post", new_callable=AsyncMock, return_value=mock_response):
            result = await c.fetch_page(FetchParams(page=1))

        assert result.has_next is True
        assert result.next_page == 2

    @pytest.mark.asyncio
    async def test_close(self):
        c = USAspendingConnector()
        c._client = AsyncMock()
        c._client.is_closed = False
        await c.close()
        c._client.aclose.assert_called_once()
