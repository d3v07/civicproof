"""Contract tests for upstream API response shapes.

These tests validate that our connector code correctly handles the expected
response structure from each data source. They do NOT make real HTTP calls —
they verify our parsing logic against fixture data that matches documented
API schemas.

If an upstream API changes its response shape, these tests should fail first,
alerting us to update the connector before it breaks in production.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from src.connectors.base import FetchParams  # noqa: E402
from src.connectors.doj import DOJConnector  # noqa: E402
from src.connectors.oversight import OversightGovConnector  # noqa: E402
from src.connectors.sec_edgar import SECEdgarConnector  # noqa: E402
from src.connectors.usaspending import USAspendingConnector  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures: minimal upstream response shapes per API documentation
# ---------------------------------------------------------------------------

USASPENDING_RESPONSE = {
    "results": [
        {
            "Award ID": "CONT_AWD_0001",
            "Recipient Name": "LOCKHEED MARTIN CORPORATION",
            "Award Amount": 2500000.00,
            "Awarding Agency": "DEPARTMENT OF DEFENSE",
            "Award Type": "Definitive Contract",
            "Start Date": "2024-01-15",
            "End Date": "2025-01-14",
            "Recipient UEI": "ABCDE12345FG",
            "Extent Competed": "FULL AND OPEN COMPETITION",
            "NAICS Code": "336411",
        },
    ],
    "page_metadata": {"total": 1, "hasNext": False},
}

SEC_EDGAR_RESPONSE = {
    "hits": {
        "total": {"value": 42},
        "hits": [
            {
                "_source": {
                    "accession_no": "0001193125-24-012345",
                    "cik": "936468",
                    "entity_name": "LOCKHEED MARTIN CORP",
                    "form_type": "10-K",
                    "file_date": "2024-02-06",
                    "period_of_report": "2023-12-31",
                    "file_num": "001-11437",
                    "file_name": "lmt-20231231.htm",
                    "display_name": "Annual Report",
                },
            },
        ],
    },
}

DOJ_RESPONSE = {
    "results": [
        {
            "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "title": (
                "Defense Contractor to Pay $19.5 Million"
                " to Settle False Claims Act Allegations"
            ),
            "date": "2024-06-15T12:00:00Z",
            "body": (
                "The Department of Justice announced today that XYZ Corp has agreed to pay "
                "$19.5 million to resolve allegations under the False Claims Act. "
                "Case No. 1:24-cv-00789 was filed in the Eastern District of Virginia."
            ),
            "url": "/opa/pr/defense-contractor-pay-settlement",
            "component": {"name": "Civil Division"},
            "topic": [{"name": "False Claims Act"}, {"name": "Fraud"}],
        },
    ],
    "pager": {"total_items": 1, "total_pages": 1},
}

OVERSIGHT_GOV_RESPONSE = {
    "results": [
        {
            "id": "OIG-2024-001",
            "title": "Audit of DOD Contract Management Practices",
            "agency": "Department of Defense",
            "report_type": "Audit",
            "published_date": "2024-03-15",
            "url": "/reports/OIG-2024-001",
            "summary": "Found significant weaknesses in contract oversight.",
            "recommendations_count": 12,
            "monetary_findings": 45000000,
            "report_number": "DODIG-2024-042",
        },
    ],
    "total": 1,
}


# ---------------------------------------------------------------------------
# USAspending contract
# ---------------------------------------------------------------------------
class TestUSAspendingContract:
    """Verifies USAspending connector handles documented API shape."""

    @pytest.mark.asyncio
    async def test_response_shape_produces_expected_artifact_keys(self):
        c = USAspendingConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = USASPENDING_RESPONSE
        mock_resp.content = b"{}"

        with unittest.mock.patch.object(
            c, "_rate_limited_post", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await c.fetch_page(FetchParams(
                query={"recipient_search_text": ["LOCKHEED"]},
            ))

        art = result.artifacts[0]
        required_keys = {
            "award_id", "recipient_name", "award_amount", "awarding_agency",
            "award_type", "start_date", "end_date", "recipient_uei",
            "extent_competed", "naics_code",
        }
        assert required_keys.issubset(set(art.keys())), (
            f"Missing keys: {required_keys - set(art.keys())}"
        )

    @pytest.mark.asyncio
    async def test_page_metadata_maps_correctly(self):
        c = USAspendingConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = USASPENDING_RESPONSE
        mock_resp.content = b"{}"

        with unittest.mock.patch.object(
            c, "_rate_limited_post", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await c.fetch_page(FetchParams())

        assert result.total_count == 1
        assert result.has_next is False

    def test_canonical_url_uses_award_id(self):
        c = USAspendingConnector()
        url = c.canonical_url({"award_id": "CONT_AWD_0001"})
        assert "CONT_AWD_0001" in url


# ---------------------------------------------------------------------------
# SEC EDGAR contract
# ---------------------------------------------------------------------------
class TestSECEdgarContract:
    """Verifies SEC EDGAR connector handles documented EFTS response shape."""

    @pytest.mark.asyncio
    async def test_response_shape_produces_expected_artifact_keys(self):
        c = SECEdgarConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = SEC_EDGAR_RESPONSE
        mock_resp.content = b"{}"

        with unittest.mock.patch.object(
            c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await c.fetch_page(FetchParams(query={"q": "LOCKHEED"}))

        art = result.artifacts[0]
        required_keys = {
            "source", "accession_number", "cik", "entity_name",
            "form_type", "file_date", "document_url",
        }
        assert required_keys.issubset(set(art.keys())), (
            f"Missing keys: {required_keys - set(art.keys())}"
        )

    @pytest.mark.asyncio
    async def test_document_url_built_from_cik_accession_filename(self):
        c = SECEdgarConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = SEC_EDGAR_RESPONSE
        mock_resp.content = b"{}"

        with unittest.mock.patch.object(
            c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await c.fetch_page(FetchParams(query={"q": "test"}))

        art = result.artifacts[0]
        assert "936468" in art["document_url"]
        assert "lmt-20231231.htm" in art["document_url"]

    @pytest.mark.asyncio
    async def test_total_count_from_nested_hits(self):
        c = SECEdgarConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = SEC_EDGAR_RESPONSE
        mock_resp.content = b"{}"

        with unittest.mock.patch.object(
            c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await c.fetch_page(FetchParams(query={"q": "test"}))

        assert result.total_count == 42


# ---------------------------------------------------------------------------
# DOJ contract
# ---------------------------------------------------------------------------
class TestDOJContract:
    """Verifies DOJ connector handles documented press releases JSON shape."""

    @pytest.mark.asyncio
    async def test_response_shape_produces_expected_artifact_keys(self):
        c = DOJConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = DOJ_RESPONSE
        mock_resp.content = b"{}"

        with unittest.mock.patch.object(
            c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await c.fetch_page(FetchParams())

        art = result.artifacts[0]
        required_keys = {
            "source", "press_release_id", "title", "date", "body",
            "extracted_amounts", "extracted_case_numbers",
            "extracted_districts", "fraud_relevant",
        }
        assert required_keys.issubset(set(art.keys())), (
            f"Missing keys: {required_keys - set(art.keys())}"
        )

    @pytest.mark.asyncio
    async def test_regex_extraction_from_body(self):
        c = DOJConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = DOJ_RESPONSE
        mock_resp.content = b"{}"

        with unittest.mock.patch.object(
            c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await c.fetch_page(FetchParams())

        art = result.artifacts[0]
        assert len(art["extracted_amounts"]) >= 1
        assert any("19.5 million" in a for a in art["extracted_amounts"])
        assert len(art["extracted_case_numbers"]) >= 1
        assert len(art["extracted_districts"]) >= 1
        assert art["fraud_relevant"] is True

    @pytest.mark.asyncio
    async def test_pager_maps_correctly(self):
        c = DOJConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = DOJ_RESPONSE
        mock_resp.content = b"{}"

        with unittest.mock.patch.object(
            c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await c.fetch_page(FetchParams())

        assert result.total_count == 1
        assert result.has_next is False


# ---------------------------------------------------------------------------
# Oversight.gov contract
# ---------------------------------------------------------------------------
class TestOversightGovContract:
    """Verifies Oversight.gov connector handles the expected response shape."""

    @pytest.mark.asyncio
    async def test_response_shape_produces_expected_artifact_keys(self):
        c = OversightGovConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = OVERSIGHT_GOV_RESPONSE
        mock_resp.content = b"{}"
        mock_resp.headers = {"content-type": "application/json"}

        with unittest.mock.patch.object(
            c, "_rate_limited_get",
            new_callable=AsyncMock, return_value=mock_resp,
        ):
            result = await c.fetch_page(FetchParams())

        art = result.artifacts[0]
        required_keys = {
            "source", "report_id", "title", "agency",
            "report_type", "published_date", "summary",
            "recommendations_count", "monetary_findings",
        }
        assert required_keys.issubset(set(art.keys())), (
            f"Missing keys: {required_keys - set(art.keys())}"
        )

    @pytest.mark.asyncio
    async def test_monetary_findings_preserved(self):
        c = OversightGovConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = OVERSIGHT_GOV_RESPONSE
        mock_resp.content = b"{}"
        mock_resp.headers = {"content-type": "application/json"}

        with unittest.mock.patch.object(
            c, "_rate_limited_get",
            new_callable=AsyncMock, return_value=mock_resp,
        ):
            result = await c.fetch_page(FetchParams())

        assert result.artifacts[0]["monetary_findings"] == 45000000

    @pytest.mark.asyncio
    async def test_total_from_dict_response(self):
        c = OversightGovConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = OVERSIGHT_GOV_RESPONSE
        mock_resp.content = b"{}"
        mock_resp.headers = {"content-type": "application/json"}

        with unittest.mock.patch.object(
            c, "_rate_limited_get",
            new_callable=AsyncMock, return_value=mock_resp,
        ):
            result = await c.fetch_page(FetchParams())

        assert result.total_count == 1


import unittest.mock  # noqa: E402
