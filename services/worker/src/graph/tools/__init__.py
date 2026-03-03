"""LangChain @tool wrappers around existing federal data connectors.

These are used by the Evidence Retrieval node's LLM to decide which
sources to query. Each tool returns raw dicts — the node handles
DB persistence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import tool


@tool
async def search_usaspending_awards(
    recipient_name: str,
    max_pages: int = 2,
) -> list[dict[str, Any]]:
    """Search USAspending.gov for federal contract awards by recipient name.
    Returns award records with amounts, agencies, dates, and competition data.
    Use for: any vendor receiving federal contracts or grants."""
    from ...connectors.usaspending import USAspendingConnector

    connector = USAspendingConnector()
    try:
        return await connector.search_by_recipient_name(recipient_name, max_pages=max_pages)
    finally:
        await connector.close()


@tool
async def search_sam_opportunities(
    keyword: str,
    posted_from: str | None = None,
) -> list[dict[str, Any]]:
    """Search SAM.gov for federal contract opportunities by keyword.
    Returns opportunity notices with solicitation numbers, agencies, and set-asides.
    Use for: checking if an entity has active or recent contract opportunities."""
    from ...connectors.sam_gov import SAMGovConnector
    from civicproof_common.config import get_settings

    settings = get_settings()
    if not settings.SAM_GOV_API_KEY:
        return [{"error": "SAM_GOV_API_KEY not configured"}]

    connector = SAMGovConnector(api_key=settings.SAM_GOV_API_KEY)
    try:
        from ...connectors.base import FetchParams
        params = FetchParams(
            query={"keyword": keyword, "posted_from": posted_from or ""},
            page=1,
            page_size=25,
        )
        result = await connector.fetch_page(params)
        return result.artifacts[:25]
    finally:
        await connector.close()


@tool
async def search_sec_filings(
    company_name: str,
    form_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search SEC EDGAR for company filings (10-K, 10-Q, 8-K, DEF 14A).
    Returns filing metadata with accession numbers, dates, and document URLs.
    Use for: publicly traded companies, entities with SEC registration."""
    from ...connectors.sec_edgar import SECEdgarConnector

    connector = SECEdgarConnector()
    try:
        return await connector.search_company_filings(
            company_name, forms=form_types, max_pages=2,
        )
    finally:
        await connector.close()


@tool
async def search_doj_press_releases(
    keywords: str | None = None,
    date_from: str | None = None,
) -> list[dict[str, Any]]:
    """Search DOJ press releases for fraud-related announcements.
    Returns press releases with titles, dates, and extracted case numbers.
    Use for: checking if an entity or individuals have been named in DOJ actions."""
    from ...connectors.doj import DOJConnector

    connector = DOJConnector()
    try:
        since = None
        if date_from:
            try:
                since = datetime.fromisoformat(date_from).replace(tzinfo=UTC)
            except ValueError:
                pass
        return await connector.search_fraud_releases(since=since, max_pages=3)
    finally:
        await connector.close()


@tool
async def search_openfec_committees(
    name: str,
) -> list[dict[str, Any]]:
    """Search OpenFEC for political action committees and campaign contributions.
    Returns committee records with treasurer names, party affiliations, and cycles.
    Use for: entities or individuals with potential political donation activity."""
    from ...connectors.openfec import OpenFECConnector
    from civicproof_common.config import get_settings

    settings = get_settings()
    if not settings.OPENFEC_API_KEY:
        return [{"error": "OPENFEC_API_KEY not configured"}]

    connector = OpenFECConnector(api_key=settings.OPENFEC_API_KEY)
    try:
        from ...connectors.base import FetchParams
        params = FetchParams(
            query={"endpoint": "committees", "q": name},
            page=1,
            page_size=20,
        )
        result = await connector.fetch_page(params)
        return result.artifacts[:20]
    finally:
        await connector.close()


@tool
async def search_oversight_reports(
    query: str,
    agency: str | None = None,
) -> list[dict[str, Any]]:
    """Search Oversight.gov for Inspector General reports.
    Returns IG reports with summaries, monetary findings, and recommendation counts.
    Use for: checking if an entity's contracting agency has relevant IG findings."""
    from ...connectors.oversight import OversightGovConnector

    connector = OversightGovConnector()
    try:
        return await connector.search_ig_reports(
            query=query, agency=agency, max_pages=2,
        )
    finally:
        await connector.close()


ALL_TOOLS = [
    search_usaspending_awards,
    search_sam_opportunities,
    search_sec_filings,
    search_doj_press_releases,
    search_openfec_committees,
    search_oversight_reports,
]
