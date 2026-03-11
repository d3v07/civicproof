"""DOJ Press Release API connector.

Endpoint: GET https://www.justice.gov/api/v1/press-releases.json
No API key required. Rate limit: 4 RPS.
Extracts: defendants, districts, statutes, settlement amounts, case numbers.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import httpx

from .base import BaseConnector, FetchParams, FetchResult

logger = logging.getLogger(__name__)

BASE_URL = "https://www.justice.gov"


class DOJConnector(BaseConnector):
    """Connector for DOJ press releases API."""

    source_id = "doj"
    rate_limit_rps = 4.0
    base_url = BASE_URL

    # Regex patterns for extracting structured data from press release body
    _AMOUNT_PATTERN = re.compile(
        r"\$[\d,]+(?:\.\d{1,2})?\s*(?:million|billion)?", re.IGNORECASE
    )
    _CASE_NUMBER_PATTERN = re.compile(
        r"(?:Case\s+(?:No\.\s*)?|No\.\s+)\d{1,2}[:-]\d{2}[:-](?:cv|cr|mc|mj|po)-\d+",
        re.IGNORECASE,
    )
    _DISTRICT_PATTERN = re.compile(
        r"(?:Eastern|Western|Northern|Southern|Central|Middle)\s+District\s+of\s+\w+",
        re.IGNORECASE,
    )

    # Topic keywords for filtering fraud-relevant releases
    FRAUD_TOPICS = [
        "false claims act",
        "procurement fraud",
        "government contract fraud",
        "kickback",
        "bid rigging",
        "wire fraud",
        "fraud",
        "qui tam",
        "civil settlement",
        "debarment",
    ]

    async def fetch_page(self, params: FetchParams) -> FetchResult:
        """Fetch a page of press releases from DOJ API."""
        query_params: dict[str, Any] = {
            "pagesize": params.page_size,
            "page": params.page - 1,  # DOJ uses 0-indexed pages
            "sort": "date",
            "direction": "DESC",
        }

        # Apply keyword filter via title parameter
        keyword = params.query.get("keyword")
        if keyword:
            query_params["parameters[title]"] = keyword

        # Apply component filter (e.g., "criminal-division", "civil-division")
        component = params.query.get("component")
        if component:
            query_params["parameters[component]"] = component

        url = f"{self.base_url}/api/v1/press_releases.json"
        try:
            response = await self._rate_limited_get(url, params=query_params)
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (401, 403, 404):
                logger.warning(
                    "doj_api_unavailable status=%d url=%s", code, url,
                )
                return FetchResult(
                    artifacts=[], total_count=0, has_next=False,
                )
            raise
        data = response.json()

        results = data.get("results", [])
        pager = data.get("pager", {})
        total = pager.get("total_items", 0)
        total_pages = pager.get("total_pages", 1)
        current_page = params.page  # 1-indexed
        # DOJ pages param is 0-indexed, but total_pages is a count.
        # current_page=1 maps to page 0, so we have pages 0..total_pages-1.
        has_next = current_page < total_pages
        next_page = current_page + 1 if has_next else None

        artifacts = []
        for record in results:
            body_text = record.get("body", "")

            # Extract structured data from press release body
            amounts = self._AMOUNT_PATTERN.findall(body_text)
            case_numbers = self._CASE_NUMBER_PATTERN.findall(body_text)
            districts = self._DISTRICT_PATTERN.findall(body_text)

            # Check fraud relevance
            body_lower = body_text.lower()
            title_lower = (record.get("title") or "").lower()
            fraud_relevant = any(
                topic in body_lower or topic in title_lower
                for topic in self.FRAUD_TOPICS
            )

            artifact = {
                "source": self.source_id,
                "press_release_id": record.get("uuid", ""),
                "title": record.get("title", ""),
                "date": record.get("date", ""),
                "body": body_text,
                "url": record.get("url", ""),
                "component": record.get("component", {}).get("name", ""),
                "topic": [t.get("name", "") for t in record.get("topic", [])],
                "extracted_amounts": amounts,
                "extracted_case_numbers": case_numbers,
                "extracted_districts": districts,
                "fraud_relevant": fraud_relevant,
            }
            artifacts.append(artifact)

        return FetchResult(
            artifacts=artifacts,
            total_count=total,
            has_next=has_next,
            next_page=next_page,
            raw_response_bytes=response.content,
        )

    async def search_fraud_releases(
        self,
        since: datetime | None = None,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Convenience: fetch fraud-related press releases."""
        all_artifacts: list[dict[str, Any]] = []
        params = FetchParams(
            query={},
            page=1,
            page_size=50,
            since=since,
        )
        for _ in range(max_pages):
            result = await self.fetch_page(params)
            fraud_artifacts = [a for a in result.artifacts if a.get("fraud_relevant")]
            all_artifacts.extend(fraud_artifacts)
            if not result.has_next or result.next_page is None:
                break
            params.page = result.next_page
        return all_artifacts

    def canonical_url(self, artifact: dict[str, Any]) -> str:
        url = artifact.get("url", "")
        if url and not url.startswith("http"):
            return f"{self.base_url}{url}"
        return url or f"{self.base_url}/press-release/{artifact.get('press_release_id', '')}"

    def doc_type(self) -> str:
        return "press_release"
