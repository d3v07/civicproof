"""USAspending.gov V2 API connector.

Endpoints used:
  POST /api/v2/search/spending_by_award/  — award search by recipient
  GET  /api/v2/awards/{id}/              — single award detail
  GET  /api/v2/recipient/                — recipient profile

No API key required. Courtesy rate limit: 5 RPS.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .base import BaseConnector, FetchParams, FetchResult

logger = logging.getLogger(__name__)

BASE_URL = "https://api.usaspending.gov"


class USAspendingConnector(BaseConnector):
    """Connector for USAspending.gov V2 API."""

    source_id = "usaspending"
    rate_limit_rps = 5.0
    base_url = BASE_URL

    # Core fields — keep small to avoid 500s on large result sets
    AWARD_FIELDS = [
        "Award ID",
        "Recipient Name",
        "Award Amount",
        "Awarding Agency",
        "Award Type",
        "Start Date",
        "End Date",
        "Recipient UEI",
        "Extent Competed",
        "NAICS Code",
    ]

    async def fetch_page(self, params: FetchParams) -> FetchResult:
        """Search awards by recipient name or other filters."""
        filters: dict[str, Any] = {}

        # Build filters from query params
        query = params.query
        if "recipient_search_text" in query:
            filters["recipient_search_text"] = query["recipient_search_text"]
        # award_type_codes is required by the API
        filters["award_type_codes"] = query.get(
            "award_type_codes", ["A", "B", "C", "D"]
        )
        if "naics_codes" in query:
            filters["naics_codes"] = [{"naics_code": c} for c in query["naics_codes"]]

        # Time range
        if params.since:
            filters["time_period"] = [
                {
                    "start_date": params.since.strftime("%Y-%m-%d"),
                    "end_date": (
                        params.until.strftime("%Y-%m-%d")
                        if params.until
                        else datetime.now().strftime("%Y-%m-%d")
                    ),
                    "date_type": "action_date",
                }
            ]

        body = {
            "filters": filters,
            "fields": self.AWARD_FIELDS,
            "page": params.page,
            "limit": params.page_size,
            "sort": "Award Amount",
            "order": "desc",
        }

        url = f"{self.base_url}/api/v2/search/spending_by_award/"
        response = await self._rate_limited_post(url, json_body=body)
        data = response.json()

        results = data.get("results", [])
        page_metadata = data.get("page_metadata", {})
        total = page_metadata.get("total", 0)
        has_next = page_metadata.get("hasNext", False)
        next_page = params.page + 1 if has_next else None

        artifacts = []
        for record in results:
            artifact = {
                "source": self.source_id,
                "award_id": record.get("Award ID", ""),
                "recipient_name": record.get("Recipient Name", ""),
                "award_amount": record.get("Award Amount"),
                "awarding_agency": record.get("Awarding Agency", ""),
                "award_type": record.get("Award Type", ""),
                "start_date": record.get("Start Date", ""),
                "end_date": record.get("End Date", ""),
                "internal_id": record.get("internal_id"),
                "generated_internal_id": record.get("generated_internal_id", ""),
                "recipient_uei": record.get("Recipient UEI", ""),
                "extent_competed": record.get("Extent Competed", ""),
                "naics_code": record.get("NAICS Code", ""),
            }
            artifacts.append(artifact)

        return FetchResult(
            artifacts=artifacts,
            total_count=total,
            has_next=has_next,
            next_page=next_page,
            raw_response_bytes=response.content,
        )

    async def fetch_award_detail(self, generated_award_id: str) -> dict[str, Any]:
        """Fetch full detail for a single award."""
        url = f"{self.base_url}/api/v2/awards/{generated_award_id}/"
        response = await self._rate_limited_get(url)
        return response.json()

    async def fetch_recipient(self, recipient_hash: str) -> dict[str, Any]:
        """Fetch recipient profile by hash/id."""
        url = f"{self.base_url}/api/v2/recipient/{recipient_hash}/"
        response = await self._rate_limited_get(url)
        return response.json()

    async def search_by_recipient_name(
        self,
        name: str,
        since: datetime | None = None,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Convenience: search awards by recipient name."""
        all_artifacts: list[dict[str, Any]] = []
        params = FetchParams(
            query={"recipient_search_text": [name]},
            page=1,
            page_size=25,
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
        award_id = artifact.get("award_id") or artifact.get("generated_internal_id", "")
        return f"{self.base_url}/api/v2/awards/{award_id}/"

    def doc_type(self) -> str:
        return "contract_award"
