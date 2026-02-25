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

    # Fields returned from award search
    AWARD_FIELDS = [
        "Award ID",
        "Recipient Name",
        "Award Amount",
        "Total Outlays",
        "Awarding Agency",
        "Awarding Sub Agency",
        "Award Type",
        "Start Date",
        "End Date",
        "recipient_id",
        "internal_id",
        "generated_internal_id",
        "Place of Performance City Code",
        "Place of Performance State Code",
        "Recipient DUNS",
        "Recipient UEI",
        "Contract Award Type",
        "Pricing Type",
        "Set Aside Type",
        "Extent Competed",
        "NAICS Code",
        "PSC Code",
    ]

    async def fetch_page(self, params: FetchParams) -> FetchResult:
        """Search awards by recipient name or other filters."""
        filters: dict[str, Any] = {}

        # Build filters from query params
        query = params.query
        if "recipient_search_text" in query:
            filters["recipient_search_text"] = query["recipient_search_text"]
        if "award_type_codes" in query:
            filters["award_type_codes"] = query["award_type_codes"]
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
                "total_outlays": record.get("Total Outlays"),
                "awarding_agency": record.get("Awarding Agency", ""),
                "awarding_sub_agency": record.get("Awarding Sub Agency", ""),
                "award_type": record.get("Award Type", ""),
                "start_date": record.get("Start Date", ""),
                "end_date": record.get("End Date", ""),
                "internal_id": record.get("internal_id"),
                "generated_internal_id": record.get("generated_internal_id", ""),
                "recipient_uei": record.get("Recipient UEI", ""),
                "recipient_duns": record.get("Recipient DUNS", ""),
                "pop_city_code": record.get("Place of Performance City Code", ""),
                "pop_state_code": record.get("Place of Performance State Code", ""),
                "contract_award_type": record.get("Contract Award Type", ""),
                "pricing_type": record.get("Pricing Type", ""),
                "set_aside_type": record.get("Set Aside Type", ""),
                "extent_competed": record.get("Extent Competed", ""),
                "naics_code": record.get("NAICS Code", ""),
                "psc_code": record.get("PSC Code", ""),
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
            page_size=100,
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
