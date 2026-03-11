"""Unit tests for all data source connectors."""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# SEC EDGAR
# ---------------------------------------------------------------------------
class TestSECEdgarConnector:
    def test_source_id(self):
        c = SECEdgarConnector()
        assert c.source_id == "sec_edgar"

    def test_doc_type(self):
        c = SECEdgarConnector()
        assert c.doc_type() == "sec_filing"

    def test_canonical_url_with_doc_url(self):
        c = SECEdgarConnector()
        url = c.canonical_url({"document_url": "https://sec.gov/Archives/abc.htm"})
        assert url == "https://sec.gov/Archives/abc.htm"

    def test_canonical_url_fallback(self):
        c = SECEdgarConnector()
        url = c.canonical_url({"accession_number": "0001234-56-789"})
        assert "0001234-56-789" in url
        assert "browse-edgar" in url

    def test_canonical_url_empty(self):
        c = SECEdgarConnector()
        url = c.canonical_url({})
        assert "browse-edgar" in url

    def test_relevant_form_types(self):
        c = SECEdgarConnector()
        assert "10-K" in c.RELEVANT_FORM_TYPES
        assert "8-K" in c.RELEVANT_FORM_TYPES
        assert "DEF 14A" in c.RELEVANT_FORM_TYPES

    @pytest.mark.asyncio
    async def test_fetch_page_parses_response(self):
        c = SECEdgarConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [{
                    "_source": {
                        "accession_no": "0001234-23-000001",
                        "cik": "12345",
                        "entity_name": "ACME Corp",
                        "form_type": "10-K",
                        "file_date": "2024-01-15",
                        "period_of_report": "2023-12-31",
                        "file_num": "001-12345",
                        "file_name": "doc.htm",
                        "display_name": "Annual Report",
                    },
                }],
            },
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(
                query={"q": "ACME Corp"},
            ))

        assert len(result.artifacts) == 1
        assert result.artifacts[0]["entity_name"] == "ACME Corp"
        assert result.artifacts[0]["form_type"] == "10-K"
        assert result.total_count == 1
        assert result.has_next is False

    @pytest.mark.asyncio
    async def test_fetch_page_pagination(self):
        c = SECEdgarConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "hits": {
                "total": {"value": 200},
                "hits": [{"_source": {"entity_name": f"Co{i}"}} for i in range(50)],
            },
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(page=1, page_size=50))

        assert result.has_next is True
        assert result.next_page == 2

    @pytest.mark.asyncio
    async def test_fetch_page_builds_doc_url(self):
        c = SECEdgarConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [{
                    "_source": {
                        "cik": "12345",
                        "accession_no": "0001-23-000001",
                        "file_name": "form10k.htm",
                    },
                }],
            },
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(query={"q": "test"}))

        assert "12345" in result.artifacts[0]["document_url"]
        assert "form10k.htm" in result.artifacts[0]["document_url"]

    @pytest.mark.asyncio
    async def test_search_company_filings(self):
        c = SECEdgarConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {"_source": {"entity_name": "ACME", "form_type": "10-K"}},
                    {"_source": {"entity_name": "ACME", "form_type": "10-Q"}},
                ],
            },
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            results = await c.search_company_filings("ACME", max_pages=1)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_close(self):
        c = SECEdgarConnector()
        c._client = AsyncMock()
        c._client.is_closed = False
        await c.close()
        c._client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# DOJ
# ---------------------------------------------------------------------------
class TestDOJConnector:
    def test_source_id(self):
        c = DOJConnector()
        assert c.source_id == "doj"

    def test_doc_type(self):
        c = DOJConnector()
        assert c.doc_type() == "press_release"

    def test_canonical_url_with_url(self):
        c = DOJConnector()
        url = c.canonical_url({"url": "/pr/some-release"})
        assert url == "https://www.justice.gov/pr/some-release"

    def test_canonical_url_absolute(self):
        c = DOJConnector()
        url = c.canonical_url({"url": "https://www.justice.gov/pr/abs"})
        assert url == "https://www.justice.gov/pr/abs"

    def test_canonical_url_fallback(self):
        c = DOJConnector()
        url = c.canonical_url({"press_release_id": "uuid-123"})
        assert "uuid-123" in url

    def test_fraud_topics(self):
        c = DOJConnector()
        assert "false claims act" in c.FRAUD_TOPICS
        assert "procurement fraud" in c.FRAUD_TOPICS

    def test_amount_regex(self):
        c = DOJConnector()
        matches = c._AMOUNT_PATTERN.findall("The company paid $1,234,567.89 million in fines.")
        assert len(matches) == 1
        assert "$1,234,567.89 million" in matches[0]

    def test_case_number_regex(self):
        c = DOJConnector()
        text = "Case No. 1:23-cv-00456 was filed"
        matches = c._CASE_NUMBER_PATTERN.findall(text)
        assert len(matches) == 1

    def test_district_regex(self):
        c = DOJConnector()
        text = "filed in the Eastern District of Virginia"
        matches = c._DISTRICT_PATTERN.findall(text)
        assert len(matches) == 1
        assert "Eastern District of Virginia" in matches[0]

    @pytest.mark.asyncio
    async def test_fetch_page_parses_response(self):
        c = DOJConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{
                "uuid": "pr-001",
                "title": "Company Settles False Claims Act Allegations",
                "date": "2024-06-15",
                "body": (
                    "Acme Corp agreed to pay $2.5 million."
                    " Case No. 1:24-cv-00789."
                    " Eastern District of Texas."
                ),
                "url": "/pr/acme-settlement",
                "component": {"name": "Civil Division"},
                "topic": [{"name": "False Claims Act"}],
            }],
            "pager": {"total_items": 1, "total_pages": 1},
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams())

        assert len(result.artifacts) == 1
        art = result.artifacts[0]
        assert art["press_release_id"] == "pr-001"
        assert art["fraud_relevant"] is True
        assert len(art["extracted_amounts"]) == 1
        assert len(art["extracted_case_numbers"]) == 1
        assert len(art["extracted_districts"]) == 1

    @pytest.mark.asyncio
    async def test_fetch_page_pagination(self):
        c = DOJConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{"uuid": "pr-1", "title": "Test", "body": ""}],
            "pager": {"total_items": 150, "total_pages": 3},
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(page=1))

        assert result.has_next is True
        assert result.next_page == 2

    @pytest.mark.asyncio
    async def test_fetch_page_last_page(self):
        c = DOJConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{"uuid": "pr-1", "title": "Test", "body": ""}],
            "pager": {"total_items": 50, "total_pages": 1},
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(page=1))

        assert result.has_next is False
        assert result.next_page is None

    @pytest.mark.asyncio
    async def test_search_fraud_releases_filters(self):
        c = DOJConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"uuid": "1", "title": "Fraud case", "body": "false claims act violation"},
                {"uuid": "2", "title": "Appointment", "body": "new director appointed"},
            ],
            "pager": {"total_items": 2, "total_pages": 1},
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            results = await c.search_fraud_releases(max_pages=1)

        # Only the fraud-relevant one should be returned
        assert len(results) == 1
        assert results[0]["press_release_id"] == "1"

    @pytest.mark.asyncio
    async def test_close(self):
        c = DOJConnector()
        c._client = AsyncMock()
        c._client.is_closed = False
        await c.close()
        c._client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Oversight.gov
# ---------------------------------------------------------------------------
class TestOversightGovConnector:
    def test_source_id(self):
        c = OversightGovConnector()
        assert c.source_id == "oversight_gov"

    def test_doc_type(self):
        c = OversightGovConnector()
        assert c.doc_type() == "ig_report"

    def test_canonical_url_with_url(self):
        c = OversightGovConnector()
        url = c.canonical_url({"url": "https://oversight.gov/reports/123"})
        assert url == "https://oversight.gov/reports/123"

    def test_canonical_url_relative(self):
        c = OversightGovConnector()
        url = c.canonical_url({"url": "/reports/456"})
        assert url == "https://www.oversight.gov/reports/456"

    def test_canonical_url_fallback(self):
        c = OversightGovConnector()
        url = c.canonical_url({"report_id": "rpt-789"})
        assert "rpt-789" in url

    def test_relevant_report_types(self):
        c = OversightGovConnector()
        assert "Audit" in c.RELEVANT_REPORT_TYPES
        assert "Investigation" in c.RELEVANT_REPORT_TYPES

    @pytest.mark.asyncio
    async def test_fetch_page_dict_response(self):
        c = OversightGovConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{
                "id": "rpt-001",
                "title": "Procurement Audit FY2024",
                "agency": "DOD",
                "report_type": "Audit",
                "published_date": "2024-03-01",
                "url": "/reports/rpt-001",
                "summary": "Found procurement irregularities.",
                "recommendations_count": 5,
                "monetary_findings": 2500000,
                "report_number": "IG-2024-001",
            }],
            "total": 1,
        }
        mock_resp.content = b"{}"
        mock_resp.headers = {"content-type": "application/json"}

        with patch.object(
            c, "_rate_limited_get",
            new_callable=AsyncMock, return_value=mock_resp,
        ):
            result = await c.fetch_page(FetchParams())

        assert len(result.artifacts) == 1
        art = result.artifacts[0]
        assert art["report_id"] == "rpt-001"
        assert art["agency"] == "DOD"
        assert art["monetary_findings"] == 2500000

    @pytest.mark.asyncio
    async def test_fetch_page_list_response(self):
        """Some Oversight.gov endpoints return a bare list."""
        c = OversightGovConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"id": "r1", "title": "Report 1"},
            {"id": "r2", "title": "Report 2"},
        ]
        mock_resp.content = b"[]"
        mock_resp.headers = {"content-type": "application/json"}

        with patch.object(
            c, "_rate_limited_get",
            new_callable=AsyncMock, return_value=mock_resp,
        ):
            result = await c.fetch_page(FetchParams(page_size=50))

        assert len(result.artifacts) == 2
        assert result.total_count == 2

    @pytest.mark.asyncio
    async def test_fetch_page_pagination(self):
        c = OversightGovConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{"id": f"r{i}"} for i in range(50)],
            "total": 200,
        }
        mock_resp.content = b"{}"
        mock_resp.headers = {"content-type": "application/json"}

        with patch.object(
            c, "_rate_limited_get",
            new_callable=AsyncMock, return_value=mock_resp,
        ):
            result = await c.fetch_page(FetchParams(page=1, page_size=50))

        assert result.has_next is True
        assert result.next_page == 2

    @pytest.mark.asyncio
    async def test_search_ig_reports(self):
        c = OversightGovConnector()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"id": "r1", "title": "Fraud Report"},
                {"id": "r2", "title": "Audit Report"},
            ],
            "total": 2,
        }
        mock_resp.content = b"{}"
        mock_resp.headers = {"content-type": "application/json"}

        with patch.object(
            c, "_rate_limited_get",
            new_callable=AsyncMock, return_value=mock_resp,
        ):
            results = await c.search_ig_reports(
                "procurement fraud", max_pages=1,
            )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_close(self):
        c = OversightGovConnector()
        c._client = AsyncMock()
        c._client.is_closed = False
        await c.close()
        c._client.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# SAM.gov (requires API key — test init validation)
# ---------------------------------------------------------------------------
class TestSAMGovConnector:
    def test_requires_api_key(self):
        # SAM.gov and OpenFEC use relative imports from connectors.base,
        # which differ from the installed path. We test the import path.
        from src.connectors.sam_gov import SAMGovConnector as SAM
        with pytest.raises(ValueError, match="SAM_GOV_API_KEY"):
            SAM(api_key="")

    def test_init_with_key(self):
        from src.connectors.sam_gov import SAMGovConnector as SAM
        c = SAM(api_key="test-key-123")
        assert c.source_id == "sam_gov"
        assert c._api_key == "test-key-123"

    def test_doc_type(self):
        from src.connectors.sam_gov import SAMGovConnector as SAM
        c = SAM(api_key="k")
        assert c.doc_type() == "contract_opportunity"

    def test_canonical_url(self):
        from src.connectors.sam_gov import SAMGovConnector as SAM
        c = SAM(api_key="k")
        url = c.canonical_url({"notice_id": "abc-123"})
        assert "abc-123" in url
        assert "sam.gov" in url

    @pytest.mark.asyncio
    async def test_fetch_page_parses_response(self):
        from src.connectors.sam_gov import SAMGovConnector as SAM
        c = SAM(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "totalRecords": 1,
            "opportunitiesData": [{
                "noticeId": "n-001",
                "title": "IT Services Contract",
                "solicitationNumber": "SOL-2024-001",
                "fullParentPathName": "DOD.ARMY",
                "naicsCode": "541512",
                "classificationCode": "D302",
                "postedDate": "2024-01-01",
                "responseDeadLine": "2024-02-01",
                "type": "o",
                "baseType": "Presolicitation",
                "typeOfSetAside": "SBA",
                "typeOfSetAsideDescription": "Small Business",
                "uiLink": "https://sam.gov/opp/n-001",
                "officeAddress": {"city": "Washington", "state": "DC"},
                "pointOfContact": [
                    {"fullName": "John Doe", "email": "j@army.mil", "type": "primary"},
                ],
                "award": {},
            }],
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams())

        assert len(result.artifacts) == 1
        art = result.artifacts[0]
        assert art["notice_id"] == "n-001"
        assert art["naics_code"] == "541512"
        assert len(art["point_of_contact"]) == 1
        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_fetch_page_pagination(self):
        from src.connectors.sam_gov import SAMGovConnector as SAM
        c = SAM(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "totalRecords": 5000,
            "opportunitiesData": [{"noticeId": f"n-{i}"} for i in range(100)],
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(page=1, page_size=100))

        assert result.has_next is True
        assert result.next_page == 2


# ---------------------------------------------------------------------------
# OpenFEC (requires API key — test init validation)
# ---------------------------------------------------------------------------
class TestOpenFECConnector:
    def test_requires_api_key(self):
        from src.connectors.openfec import OpenFECConnector as FEC
        with pytest.raises(ValueError, match="OPENFEC_API_KEY"):
            FEC(api_key="")

    def test_init_with_key(self):
        from src.connectors.openfec import OpenFECConnector as FEC
        c = FEC(api_key="test-fec-key")
        assert c.source_id == "openfec"
        assert c._api_key == "test-fec-key"

    def test_doc_type(self):
        from src.connectors.openfec import OpenFECConnector as FEC
        c = FEC(api_key="k")
        assert c.doc_type() == "fec_record"

    def test_canonical_url_committee(self):
        from src.connectors.openfec import OpenFECConnector as FEC
        c = FEC(api_key="k")
        url = c.canonical_url({"committee_id": "C00123456"})
        assert "C00123456" in url
        assert "committees" in url

    def test_canonical_url_receipt(self):
        from src.connectors.openfec import OpenFECConnector as FEC
        c = FEC(api_key="k")
        url = c.canonical_url({"sub_id": "12345", "committee_id": "C00123"})
        assert "12345" in url
        assert "receipts" in url

    @pytest.mark.asyncio
    async def test_fetch_page_committees(self):
        from src.connectors.openfec import OpenFECConnector as FEC
        c = FEC(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "pagination": {"count": 1, "pages": 1},
            "results": [{
                "committee_id": "C00123456",
                "name": "ACME PAC",
                "committee_type": "Q",
                "designation": "B",
                "organization_type": "C",
                "state": "VA",
                "party": "DEM",
                "treasurer_name": "Jane Smith",
                "first_file_date": "2020-01-15",
                "cycles": [2020, 2022],
                "sponsor_candidate_ids": [],
            }],
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(query={"endpoint": "committees"}))

        assert len(result.artifacts) == 1
        assert result.artifacts[0]["committee_id"] == "C00123456"
        assert result.artifacts[0]["name"] == "ACME PAC"

    @pytest.mark.asyncio
    async def test_fetch_page_schedule_a(self):
        from src.connectors.openfec import OpenFECConnector as FEC
        c = FEC(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "pagination": {"count": 1, "pages": 1},
            "results": [{
                "sub_id": 99001,
                "committee_id": "C00123456",
                "committee": {"name": "ACME PAC"},
                "contributor_name": "John Exec",
                "contributor_employer": "ACME Corp",
                "contributor_occupation": "CEO",
                "contributor_city": "Arlington",
                "contributor_state": "VA",
                "contribution_receipt_amount": 5000,
                "contribution_receipt_date": "2024-03-15",
                "memo_text": "",
                "line_number": "11AI",
            }],
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(query={"endpoint": "schedules/schedule_a"}))

        assert len(result.artifacts) == 1
        art = result.artifacts[0]
        assert art["contributor_name"] == "John Exec"
        assert art["contribution_receipt_amount"] == 5000
        assert art["sub_id"] == "99001"

    @pytest.mark.asyncio
    async def test_fetch_page_pagination(self):
        from src.connectors.openfec import OpenFECConnector as FEC
        c = FEC(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "pagination": {"count": 300, "pages": 3},
            "results": [{"committee_id": f"C{i}"} for i in range(100)],
        }
        mock_resp.content = b"{}"

        with patch.object(c, "_rate_limited_get", new_callable=AsyncMock, return_value=mock_resp):
            result = await c.fetch_page(FetchParams(page=1, query={"endpoint": "committees"}))

        assert result.has_next is True
        assert result.next_page == 2
