"""SAM.gov Opportunities API connector.

Source: https://api.sam.gov/opportunities/v2/search
Rate limit: 4 RPS (HARD CONSTRAINT per data-engineer agent spec)
Auth: API key required (SAM_GOV_API_KEY env var)
Pagination: limit=1000 max per page

IMPORTANT: FAPIIS data is official-use-only — out of scope per data-engineer agent.
This connector only ingests public opportunity notices.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import BaseConnector, FetchParams, FetchResult

logger = logging.getLogger(__name__)


class SAMGovConnector(BaseConnector):
    """Connector for SAM.gov public opportunities API.

    Fetches active and archived contract opportunities.
    Schedule: daily 04:00 UTC (active), weekly Sunday (archived).
    """

    source_id = "sam_gov"
    rate_limit_rps = 4.0
    base_url = "https://api.sam.gov/opportunities/v2/search"

    # Hard pagination limit per SAM.gov API docs
    MAX_PAGE_SIZE = 1000

    def __init__(
        self,
        api_key: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not api_key:
            raise ValueError(
                "SAM_GOV_API_KEY is required. Register at "
                "https://open.gsa.gov/api/get-opportunities-public-api/"
            )
        self._api_key = api_key

    async def fetch_page(self, params: FetchParams) -> FetchResult:
        """Fetch a page of contract opportunities from SAM.gov."""
        query_params: dict[str, Any] = {
            "api_key": self._api_key,
            "limit": min(params.page_size, self.MAX_PAGE_SIZE),
            "offset": (params.page - 1) * min(params.page_size, self.MAX_PAGE_SIZE),
            "postedFrom": (
                params.since.strftime("%m/%d/%Y")
                if params.since
                else "01/01/2020"
            ),
        }

        if params.until:
            query_params["postedTo"] = params.until.strftime("%m/%d/%Y")

        # Merge any extra query filters
        if params.query:
            if "naics" in params.query:
                query_params["ncode"] = params.query["naics"]
            if "keyword" in params.query:
                query_params["q"] = params.query["keyword"]
            if "ptype" in params.query:
                query_params["ptype"] = params.query["ptype"]

        response = await self._rate_limited_get(self.base_url, params=query_params)
        data = response.json()

        opportunities = data.get("opportunitiesData", [])
        total_records = data.get("totalRecords", 0)

        artifacts = []
        for opp in opportunities:
            artifacts.append({
                "notice_id": opp.get("noticeId", ""),
                "title": opp.get("title", ""),
                "sol_number": opp.get("solicitationNumber", ""),
                "department": opp.get("fullParentPathName", ""),
                "naics_code": opp.get("naicsCode", ""),
                "classification_code": opp.get("classificationCode", ""),
                "posted_date": opp.get("postedDate", ""),
                "response_deadline": opp.get("responseDeadLine", ""),
                "type": opp.get("type", ""),
                "base_type": opp.get("baseType", ""),
                "set_aside": opp.get("typeOfSetAside", ""),
                "set_aside_description": opp.get("typeOfSetAsideDescription", ""),
                "description_url": opp.get("uiLink", ""),
                "office_address": opp.get("officeAddress", {}),
                "point_of_contact": [
                    {
                        "name": poc.get("fullName", ""),
                        "email": poc.get("email", ""),
                        "type": poc.get("type", ""),
                    }
                    for poc in opp.get("pointOfContact", [])
                ],
                "award": opp.get("award", {}),
            })

        page_size = min(params.page_size, self.MAX_PAGE_SIZE)
        offset = (params.page - 1) * page_size
        has_next = (offset + len(opportunities)) < total_records

        logger.info(
            "sam_gov_fetch page=%d artifacts=%d total=%d",
            params.page,
            len(artifacts),
            total_records,
        )

        return FetchResult(
            artifacts=artifacts,
            total_count=total_records,
            has_next=has_next,
            next_page=params.page + 1 if has_next else None,
            raw_response_bytes=response.content,
        )

    def canonical_url(self, artifact: dict[str, Any]) -> str:
        notice_id = artifact.get("notice_id", "")
        return f"https://sam.gov/opp/{notice_id}"

    def doc_type(self) -> str:
        return "contract_opportunity"
