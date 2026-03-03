"""Federal Data MCP Server — exposes 6 federal connectors as MCP tools.

Run standalone:
    python -m graph.mcp.federal_data

Or import the `mcp_app` for programmatic use / testing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp_app = FastMCP(
    "CivicProof Federal Data",
    instructions="Query 6 federal data sources for procurement investigations",
)


@mcp_app.tool()
async def search_usaspending_awards(
    recipient_name: str,
    max_pages: int = 2,
) -> str:
    """Search USAspending.gov for federal contract awards by recipient name.
    Returns award records with amounts, agencies, dates, and competition data."""
    from ...connectors.usaspending import USAspendingConnector

    connector = USAspendingConnector()
    try:
        results = await connector.search_by_recipient_name(recipient_name, max_pages=max_pages)
        return json.dumps(results, default=str)
    finally:
        await connector.close()


@mcp_app.tool()
async def search_sam_opportunities(
    keyword: str,
    posted_from: str | None = None,
) -> str:
    """Search SAM.gov for federal contract opportunities by keyword.
    Returns opportunity notices with solicitation numbers and agencies."""
    from ...connectors.sam_gov import SAMGovConnector
    from ...connectors.base import FetchParams
    from civicproof_common.config import get_settings

    settings = get_settings()
    if not settings.SAM_GOV_API_KEY:
        return json.dumps({"error": "SAM_GOV_API_KEY not configured"})

    connector = SAMGovConnector(api_key=settings.SAM_GOV_API_KEY)
    try:
        params = FetchParams(
            query={"keyword": keyword, "posted_from": posted_from or ""},
            page=1,
            page_size=25,
        )
        result = await connector.fetch_page(params)
        return json.dumps(result.artifacts[:25], default=str)
    finally:
        await connector.close()


@mcp_app.tool()
async def search_sec_filings(
    company_name: str,
    form_types: list[str] | None = None,
) -> str:
    """Search SEC EDGAR for company filings (10-K, 10-Q, 8-K, DEF 14A).
    Returns filing metadata with accession numbers and document URLs."""
    from ...connectors.sec_edgar import SECEdgarConnector

    connector = SECEdgarConnector()
    try:
        results = await connector.search_company_filings(
            company_name, forms=form_types, max_pages=2,
        )
        return json.dumps(results, default=str)
    finally:
        await connector.close()


@mcp_app.tool()
async def search_doj_press_releases(
    keywords: str | None = None,
    date_from: str | None = None,
) -> str:
    """Search DOJ press releases for fraud-related announcements.
    Returns press releases with titles, dates, and case numbers."""
    from ...connectors.doj import DOJConnector

    connector = DOJConnector()
    try:
        since = None
        if date_from:
            try:
                since = datetime.fromisoformat(date_from).replace(tzinfo=UTC)
            except ValueError:
                pass
        results = await connector.search_fraud_releases(since=since, max_pages=3)
        return json.dumps(results, default=str)
    finally:
        await connector.close()


@mcp_app.tool()
async def search_openfec_committees(
    name: str,
) -> str:
    """Search OpenFEC for political action committees and campaign contributions.
    Returns committee records with treasurer names and party affiliations."""
    from ...connectors.openfec import OpenFECConnector
    from ...connectors.base import FetchParams
    from civicproof_common.config import get_settings

    settings = get_settings()
    if not settings.OPENFEC_API_KEY:
        return json.dumps({"error": "OPENFEC_API_KEY not configured"})

    connector = OpenFECConnector(api_key=settings.OPENFEC_API_KEY)
    try:
        params = FetchParams(
            query={"endpoint": "committees", "q": name},
            page=1,
            page_size=20,
        )
        result = await connector.fetch_page(params)
        return json.dumps(result.artifacts[:20], default=str)
    finally:
        await connector.close()


@mcp_app.tool()
async def search_oversight_reports(
    query: str,
    agency: str | None = None,
) -> str:
    """Search Oversight.gov for Inspector General reports.
    Returns IG reports with summaries and monetary findings."""
    from ...connectors.oversight import OversightGovConnector

    connector = OversightGovConnector()
    try:
        results = await connector.search_ig_reports(
            query=query, agency=agency, max_pages=2,
        )
        return json.dumps(results, default=str)
    finally:
        await connector.close()


if __name__ == "__main__":
    mcp_app.run()
