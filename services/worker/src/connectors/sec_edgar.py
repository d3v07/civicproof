"""SEC EDGAR full-text search connector.

Endpoint: GET https://efts.sec.gov/LATEST/search-index
Strict rate limit: 10 RPS enforced by SEC fair access policy.
User-Agent MUST include contact email per SEC developer policy.
No API key required.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .base import BaseConnector, FetchParams, FetchResult

logger = logging.getLogger(__name__)

BASE_URL = "https://efts.sec.gov/LATEST"
EDGAR_BASE = "https://www.sec.gov"

# Override UA for SEC — must include email
SEC_USER_AGENT = "CivicProof/0.1 (contact: civicproof@d3v07.dev)"


class SECEdgarConnector(BaseConnector):
    """Connector for SEC EDGAR full-text search.

    Fetches 10-K, 10-Q, 8-K, and DEF 14A filings related to
    government contractors for cross-referencing with federal awards.
    """

    source_id = "sec_edgar"
    rate_limit_rps = 10.0
    base_url = EDGAR_BASE

    # Filing types most relevant for federal contractor analysis
    RELEVANT_FORM_TYPES = [
        "10-K",     # Annual report
        "10-Q",     # Quarterly report
        "8-K",      # Current report / material events
        "DEF 14A",  # Proxy statement (officer compensation)
        "S-1",      # IPO filing
    ]

    async def _get_client(self):
        """Override to use SEC-specific User-Agent."""
        import httpx

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": SEC_USER_AGENT},
                timeout=httpx.Timeout(connect=10, read=30, write=30, pool=30),
            )
        return self._client

    async def fetch_page(self, params: FetchParams) -> FetchResult:
        """Search EDGAR full-text search index."""
        query_params: dict[str, Any] = {
            "q": params.query.get("q", "government contract"),
            "from": (params.page - 1) * params.page_size,
            "size": params.page_size,
        }

        # Form type filter
        forms = params.query.get("forms", self.RELEVANT_FORM_TYPES)
        if forms:
            query_params["forms"] = ",".join(forms)

        # Date range
        if params.since:
            query_params["startdt"] = params.since.strftime("%Y-%m-%d")
        if params.until:
            query_params["enddt"] = params.until.strftime("%Y-%m-%d")

        url = f"{BASE_URL}/search-index"
        response = await self._rate_limited_get(url, params=query_params)
        data = response.json()

        hits = data.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        results = hits.get("hits", [])

        artifacts = []
        for hit in results:
            source_data = hit.get("_source", {})
            file_date = source_data.get("file_date", "")
            form_type = source_data.get("form_type", "")
            entity_name = source_data.get("entity_name", "")
            file_num = source_data.get("file_num", "")
            period_of_report = source_data.get("period_of_report", "")

            # Build document URL
            accession = source_data.get("accession_no", "").replace("-", "")
            file_name = source_data.get("file_name", "")
            cik = source_data.get("cik", "")

            doc_url = ""
            if cik and accession and file_name:
                doc_url = (
                    f"{EDGAR_BASE}/Archives/edgar/data/{cik}/{accession}/{file_name}"
                )

            artifact = {
                "source": self.source_id,
                "accession_number": source_data.get("accession_no", ""),
                "cik": cik,
                "entity_name": entity_name,
                "form_type": form_type,
                "file_date": file_date,
                "period_of_report": period_of_report,
                "file_number": file_num,
                "document_url": doc_url,
                "description": source_data.get("display_name", ""),
            }
            artifacts.append(artifact)

        has_next = (params.page * params.page_size) < total
        next_page = params.page + 1 if has_next else None

        return FetchResult(
            artifacts=artifacts,
            total_count=total,
            has_next=has_next,
            next_page=next_page,
            raw_response_bytes=response.content,
        )

    async def search_company_filings(
        self,
        company_name: str,
        forms: list[str] | None = None,
        since: datetime | None = None,
        max_pages: int = 3,
    ) -> list[dict[str, Any]]:
        """Convenience: search filings for a specific company."""
        all_artifacts: list[dict[str, Any]] = []
        params = FetchParams(
            query={
                "q": f'"{company_name}"',
                "forms": forms or self.RELEVANT_FORM_TYPES,
            },
            page=1,
            page_size=50,
            since=since,
        )
        for _ in range(max_pages):
            result = await self.fetch_page(params)
            all_artifacts.extend(result.artifacts)
            if not result.has_next or result.next_page is None:
                break
            params.page = result.next_page
        return all_artifacts

    def canonical_url(self, artifact: dict[str, Any]) -> str:
        doc_url = artifact.get("document_url", "")
        if doc_url:
            return doc_url
        accession = artifact.get("accession_number", "")
        return f"{EDGAR_BASE}/cgi-bin/browse-edgar?action=getcompany&accession={accession}"

    def doc_type(self) -> str:
        return "sec_filing"
