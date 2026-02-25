"""Oversight.gov IG report parser.

Extracts structured data from Inspector General reports:
- Agency and report type
- Recommendations and monetary findings
- Keywords relevant to procurement fraud
"""

from __future__ import annotations

import re
from typing import Any


# Procurement fraud keywords for relevance scoring
_PROCUREMENT_KEYWORDS = [
    "procurement fraud",
    "contract fraud",
    "false claim",
    "overbilling",
    "cost mischarging",
    "defective pricing",
    "product substitution",
    "kickback",
    "bid rigging",
    "conflict of interest",
    "waste",
    "abuse",
    "mismanagement",
    "suspension",
    "debarment",
]

_AMOUNT_PATTERN = re.compile(
    r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(million|billion|thousand)?",
    re.IGNORECASE,
)


def parse_ig_report(data: dict[str, Any]) -> dict[str, Any]:
    """Parse an Oversight.gov IG report into normalized structured data.

    Args:
        data: Raw report data from the Oversight connector or stored JSON.

    Returns:
        Normalized structure with agency, findings, and relevance.
    """
    title = data.get("title", "")
    summary = data.get("summary", "")
    full_text = f"{title}\n{summary}"

    # Relevance scoring
    relevance = _compute_relevance(full_text)

    # Extract monetary amounts from summary
    amounts = _extract_amounts(full_text)

    # Collect entity mentions
    entities = _collect_entity_mentions(data)

    return {
        "doc_type": "ig_report",
        "source": "oversight_gov",
        "report": {
            "report_id": data.get("report_id", ""),
            "title": title,
            "agency": data.get("agency", ""),
            "report_type": data.get("report_type", ""),
            "published_date": data.get("published_date", ""),
            "report_number": data.get("report_number", ""),
            "url": data.get("url", ""),
        },
        "findings": {
            "summary": summary,
            "recommendations_count": data.get("recommendations_count", 0),
            "monetary_findings": data.get("monetary_findings", 0),
            "extracted_amounts": amounts,
        },
        "procurement_relevance": relevance,
        "entities_found": entities,
    }


def _compute_relevance(text: str) -> dict[str, Any]:
    """Score relevance to procurement fraud."""
    text_lower = text.lower()
    matches = [kw for kw in _PROCUREMENT_KEYWORDS if kw in text_lower]
    return {
        "is_relevant": len(matches) > 0,
        "keyword_matches": matches,
        "relevance_score": min(len(matches) / 3.0, 1.0),
    }


def _extract_amounts(text: str) -> list[dict[str, Any]]:
    """Extract monetary amounts from text."""
    amounts = []
    for match in _AMOUNT_PATTERN.finditer(text):
        raw_number = match.group(1).replace(",", "")
        multiplier_text = (match.group(2) or "").lower()
        try:
            value = float(raw_number)
        except ValueError:
            continue
        multipliers = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
        value *= multipliers.get(multiplier_text, 1)
        amounts.append({"raw_text": match.group(0).strip(), "value_usd": value})
    return amounts


def _collect_entity_mentions(data: dict[str, Any]) -> list[dict[str, str]]:
    """Collect entity mentions from report data."""
    mentions = []

    agency = data.get("agency", "")
    if agency:
        mentions.append({"name": agency, "type": "government_agency", "role": "inspected_agency"})

    return mentions
