"""OpenFEC API connector.

Source: https://api.open.fec.gov/v1/
Rate limit: 1000 calls/hour with API key (HARD CONSTRAINT per data-engineer agent spec)
Auth: API key required (OPENFEC_API_KEY env var)
Schedule: daily 05:00 UTC

Fetches committee and candidate data related to government contractors
for cross-referencing political contribution patterns.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import BaseConnector, FetchParams, FetchResult

logger = logging.getLogger(__name__)


class OpenFECConnector(BaseConnector):
    """Connector for the OpenFEC API.

    Fetches committee and individual contribution data.
    Rate limit: ~0.28 RPS (1000/hour), with burst of 5.
    """

    source_id = "openfec"
    # 1000 calls per hour = ~0.28 per second
    rate_limit_rps = 0.28
    base_url = "https://api.open.fec.gov/v1"

    # FEC page size max
    MAX_PAGE_SIZE = 100

    def __init__(
        self,
        api_key: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not api_key:
            raise ValueError(
                "OPENFEC_API_KEY is required. Register at "
                "https://api.open.fec.gov/developers/"
            )
        self._api_key = api_key

    async def fetch_page(self, params: FetchParams) -> FetchResult:
        """Fetch a page of committee/contribution data from OpenFEC."""
        endpoint = params.query.get("endpoint", "committees")
        url = f"{self.base_url}/{endpoint}/"

        query_params: dict[str, Any] = {
            "api_key": self._api_key,
            "per_page": min(params.page_size, self.MAX_PAGE_SIZE),
            "page": params.page,
            "sort_hide_null": "true",
        }

        # Add date filters
        if params.since:
            # Different endpoints use different date fields
            if endpoint == "schedules/schedule_a":
                query_params["min_date"] = params.since.strftime("%Y-%m-%d")
            elif endpoint == "committees":
                query_params["min_first_file_date"] = params.since.strftime("%Y-%m-%d")

        if params.until:
            if endpoint == "schedules/schedule_a":
                query_params["max_date"] = params.until.strftime("%Y-%m-%d")

        # Apply search filters
        if params.query:
            if "committee_type" in params.query:
                query_params["committee_type"] = params.query["committee_type"]
            if "contributor_name" in params.query:
                query_params["contributor_name"] = params.query["contributor_name"]
            if "employer" in params.query:
                query_params["contributor_employer"] = params.query["employer"]
            if "min_amount" in params.query:
                query_params["min_amount"] = params.query["min_amount"]

        response = await self._rate_limited_get(url, params=query_params)
        data = response.json()

        pagination = data.get("pagination", {})
        results = data.get("results", [])
        total_count = pagination.get("count", 0)
        total_pages = pagination.get("pages", 1)

        artifacts = []
        for record in results:
            if endpoint == "committees":
                artifacts.append({
                    "committee_id": record.get("committee_id", ""),
                    "name": record.get("name", ""),
                    "committee_type": record.get("committee_type", ""),
                    "designation": record.get("designation", ""),
                    "organization_type": record.get("organization_type", ""),
                    "state": record.get("state", ""),
                    "party": record.get("party", ""),
                    "treasurer_name": record.get("treasurer_name", ""),
                    "first_file_date": record.get("first_file_date", ""),
                    "cycles": record.get("cycles", []),
                    "sponsor_candidate_ids": record.get("sponsor_candidate_ids", []),
                })
            elif endpoint == "schedules/schedule_a":
                artifacts.append({
                    "sub_id": str(record.get("sub_id", "")),
                    "committee_id": record.get("committee_id", ""),
                    "committee_name": record.get("committee", {}).get("name", ""),
                    "contributor_name": record.get("contributor_name", ""),
                    "contributor_employer": record.get("contributor_employer", ""),
                    "contributor_occupation": record.get("contributor_occupation", ""),
                    "contributor_city": record.get("contributor_city", ""),
                    "contributor_state": record.get("contributor_state", ""),
                    "contribution_receipt_amount": record.get("contribution_receipt_amount", 0),
                    "contribution_receipt_date": record.get("contribution_receipt_date", ""),
                    "memo_text": record.get("memo_text", ""),
                    "line_number": record.get("line_number", ""),
                })
            else:
                # Generic fallback
                artifacts.append(record)

        has_next = params.page < total_pages

        logger.info(
            "openfec_fetch endpoint=%s page=%d/%d artifacts=%d total=%d",
            endpoint,
            params.page,
            total_pages,
            len(artifacts),
            total_count,
        )

        return FetchResult(
            artifacts=artifacts,
            total_count=total_count,
            has_next=has_next,
            next_page=params.page + 1 if has_next else None,
            raw_response_bytes=response.content,
        )

    def canonical_url(self, artifact: dict[str, Any]) -> str:
        committee_id = artifact.get("committee_id", "")
        sub_id = artifact.get("sub_id", "")
        if sub_id:
            return f"https://api.open.fec.gov/receipts/{sub_id}"
        return f"https://api.open.fec.gov/committees/{committee_id}"

    def doc_type(self) -> str:
        return "fec_record"
