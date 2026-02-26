"""SEC EDGAR filing parser.

Extracts structured data from SEC filings metadata:
- Filing entity identity (CIK, company name)
- Filing type and dates
- Officer/director names from proxy statements
- Business segments related to government contracting
"""

from __future__ import annotations

from typing import Any

# Government contracting keywords for relevance scoring
_GOV_CONTRACT_KEYWORDS = [
    "government contract",
    "federal contract",
    "defense contract",
    "department of defense",
    "dod",
    "department of homeland security",
    "dhs",
    "usaid",
    "fema",
    "gsa",
    "general services administration",
    "procurement",
    "sole source",
    "cost-plus",
    "far ",  # Federal Acquisition Regulation
    "dfars",
    "government customer",
    "government revenue",
    "classified program",
]


def parse_sec_filing(data: dict[str, Any]) -> dict[str, Any]:
    """Parse a SEC EDGAR filing artifact into normalized structured data.

    Args:
        data: Raw filing data from the SEC EDGAR connector or stored JSON.

    Returns:
        Normalized structure with filing details, entity info, and relevance.
    """
    entity_name = data.get("entity_name", "")
    data.get("form_type", "")
    description = data.get("description", "")

    # Determine government contracting relevance
    full_text = f"{entity_name} {description}".lower()
    relevance = _compute_gov_relevance(full_text)

    # Extract entity information
    entity = _extract_entity(data)

    # Extract filing details
    filing_details = _extract_filing_details(data)

    # Collect entity mentions
    entities_found = _collect_entity_mentions(data)

    return {
        "doc_type": "sec_filing",
        "source": "sec_edgar",
        "entity": entity,
        "filing_details": filing_details,
        "gov_contract_relevance": relevance,
        "entities_found": entities_found,
    }


def _extract_entity(data: dict[str, Any]) -> dict[str, Any]:
    """Extract the filing entity information."""
    return {
        "name": data.get("entity_name", ""),
        "cik": data.get("cik", ""),
        "file_number": data.get("file_number", ""),
        "sic_code": data.get("sic_code", ""),
    }


def _extract_filing_details(data: dict[str, Any]) -> dict[str, Any]:
    """Extract filing metadata."""
    return {
        "accession_number": data.get("accession_number", ""),
        "form_type": data.get("form_type", ""),
        "file_date": data.get("file_date", ""),
        "period_of_report": data.get("period_of_report", ""),
        "document_url": data.get("document_url", ""),
        "description": data.get("description", ""),
    }


def _compute_gov_relevance(text: str) -> dict[str, Any]:
    """Score relevance to government contracting."""
    matches = [kw for kw in _GOV_CONTRACT_KEYWORDS if kw in text]
    return {
        "is_relevant": len(matches) > 0,
        "keyword_matches": matches,
        "relevance_score": min(len(matches) / 3.0, 1.0),
    }


def _collect_entity_mentions(data: dict[str, Any]) -> list[dict[str, str]]:
    """Collect entity mentions from filing data."""
    mentions = []

    name = data.get("entity_name", "")
    if name:
        mentions.append({"name": name, "type": "vendor", "role": "filer"})

    return mentions
