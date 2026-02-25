"""Oversight.gov connector for Inspector General reports.

Oversight.gov provides public access to Inspector General reports
from across the federal government.
Courtesy rate limit: 2 RPS. No API key required.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .base import BaseConnector, FetchParams, FetchResult

logger = logging.getLogger(__name__)

BASE_URL = "https://www.oversight.gov"


class OversightGovConnector(BaseConnector):
    """Connector for Oversight.gov IG reports."""

    source_id = "oversight_gov"
    rate_limit_rps = 2.0
    base_url = BASE_URL

    # Report types of interest for procurement fraud
    RELEVANT_REPORT_TYPES = [
        "Audit",
        "Inspection / Evaluation",
        "Investigation",
        "Semiannual Report",
        "Other",
    ]

    async def fetch_page(self, params: FetchParams) -> FetchResult:
        """Fetch IG reports from Oversight.gov.

        Note: Oversight.gov does not have a well-documented public API.
        This connector targets the search/report endpoints that return
        structured data. If the API shape changes, contract tests will fail.
        """
        query_params: dict[str, Any] = {
            "page": params.page - 1,
            "size": params.page_size,
        }

        if params.query.get("q"):
            query_params["q"] = params.query["q"]

        agency = params.query.get("agency")
        if agency:
            query_params["agency"] = agency

        report_type = params.query.get("report_type")
        if report_type:
            query_params["report_type"] = report_type

        url = f"{self.base_url}/api/reports"
        response = await self._rate_limited_get(url, params=query_params)
        data = response.json()

        reports = data if isinstance(data, list) else data.get("results", [])
        total = data.get("total", len(reports)) if isinstance(data, dict) else len(reports)

        artifacts = []
        for report in reports:
            artifact = {
                "source": self.source_id,
                "report_id": report.get("id", ""),
                "title": report.get("title", ""),
                "agency": report.get("agency", ""),
                "report_type": report.get("report_type", ""),
                "published_date": report.get("published_date", ""),
                "url": report.get("url", ""),
                "summary": report.get("summary", ""),
                "recommendations_count": report.get("recommendations_count", 0),
                "monetary_findings": report.get("monetary_findings", 0),
                "report_number": report.get("report_number", ""),
            }
            artifacts.append(artifact)

        has_next = len(reports) >= params.page_size
        next_page = params.page + 1 if has_next else None

        return FetchResult(
            artifacts=artifacts,
            total_count=total,
            has_next=has_next,
            next_page=next_page,
            raw_response_bytes=response.content,
        )

    async def search_ig_reports(
        self,
        query: str = "procurement fraud",
        agency: str | None = None,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Convenience: search IG reports for fraud-related topics."""
        all_artifacts: list[dict[str, Any]] = []
        params = FetchParams(
            query={"q": query, "agency": agency} if agency else {"q": query},
            page=1,
            page_size=50,
        )
        for _ in range(max_pages):
            result = await self.fetch_page(params)
            all_artifacts.extend(result.artifacts)
            if not result.has_next or result.next_page is None:
                break
            params.page = result.next_page
        return all_artifacts

    def canonical_url(self, artifact: dict[str, Any]) -> str:
        url = artifact.get("url", "")
        if url:
            return url if url.startswith("http") else f"{self.base_url}{url}"
        report_id = artifact.get("report_id", "")
        return f"{self.base_url}/reports/{report_id}"

    def doc_type(self) -> str:
        return "ig_report"
