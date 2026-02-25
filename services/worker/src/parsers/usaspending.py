"""USAspending award parser.

Extracts structured entity information from USAspending.gov award data:
- Recipient/vendor identity (name, UEI, DUNS, CAGE)
- Award details (amount, type, dates, agency)
- Place of performance vs vendor location
- Competition and set-aside status
"""

from __future__ import annotations

from typing import Any


def parse_usaspending_award(data: dict[str, Any]) -> dict[str, Any]:
    """Parse a USAspending award artifact into normalized structured data.

    Args:
        data: Raw award data dict from the USAspending connector or stored JSON.

    Returns:
        Normalized structure with entities, award_details, and risk indicators.
    """
    # Extract recipient identity
    recipient = _extract_recipient(data)

    # Extract award details
    award_details = _extract_award_details(data)

    # Extract place of performance
    pop = _extract_place_of_performance(data)

    # Extract competition info
    competition = _extract_competition_info(data)

    # Compute basic risk indicators
    risk_indicators = _compute_risk_indicators(award_details, competition)

    return {
        "doc_type": "contract_award",
        "source": "usaspending",
        "recipient": recipient,
        "award_details": award_details,
        "place_of_performance": pop,
        "competition": competition,
        "risk_indicators": risk_indicators,
        "entities_found": _collect_entity_mentions(data),
    }


def _extract_recipient(data: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize recipient/vendor identity."""
    recipient_data = data.get("recipient", {}) if isinstance(data.get("recipient"), dict) else {}
    return {
        "name": (
            data.get("recipient_name")
            or recipient_data.get("recipient_name")
            or data.get("Recipient Name", "")
        ),
        "uei": (
            data.get("recipient_uei")
            or recipient_data.get("recipient_uei")
            or data.get("Recipient UEI", "")
        ),
        "duns": (
            data.get("recipient_duns")
            or recipient_data.get("recipient_duns")
            or data.get("Recipient DUNS", "")
        ),
        "parent_name": recipient_data.get("parent_recipient_name", ""),
        "parent_uei": recipient_data.get("parent_recipient_uei", ""),
        "business_types": recipient_data.get("business_types", []),
        "location": {
            "address_line1": recipient_data.get("location", {}).get("address_line1", ""),
            "city": recipient_data.get("location", {}).get("city_name", ""),
            "state": recipient_data.get("location", {}).get("state_code", ""),
            "zip": recipient_data.get("location", {}).get("zip5", ""),
            "country": recipient_data.get("location", {}).get("country_code", "USA"),
        },
    }


def _extract_award_details(data: dict[str, Any]) -> dict[str, Any]:
    """Extract core award details."""
    return {
        "award_id": data.get("award_id") or data.get("Award ID", ""),
        "generated_internal_id": data.get("generated_internal_id", ""),
        "award_amount": _safe_float(data.get("award_amount") or data.get("Award Amount")),
        "total_outlays": _safe_float(data.get("total_outlays") or data.get("Total Outlays")),
        "award_type": data.get("award_type") or data.get("Award Type", ""),
        "contract_award_type": data.get("contract_award_type") or data.get("Contract Award Type", ""),
        "awarding_agency": data.get("awarding_agency") or data.get("Awarding Agency", ""),
        "awarding_sub_agency": data.get("awarding_sub_agency") or data.get("Awarding Sub Agency", ""),
        "funding_agency": data.get("funding_agency", ""),
        "start_date": data.get("start_date") or data.get("Start Date", ""),
        "end_date": data.get("end_date") or data.get("End Date", ""),
        "naics_code": data.get("naics_code") or data.get("NAICS Code", ""),
        "naics_description": data.get("naics_description", ""),
        "psc_code": data.get("psc_code") or data.get("PSC Code", ""),
    }


def _extract_place_of_performance(data: dict[str, Any]) -> dict[str, Any]:
    """Extract place of performance details."""
    pop = data.get("place_of_performance", {}) if isinstance(data.get("place_of_performance"), dict) else {}
    return {
        "city": pop.get("city_name") or data.get("pop_city_code", ""),
        "state": pop.get("state_code") or data.get("pop_state_code", ""),
        "zip": pop.get("zip5", ""),
        "country": pop.get("country_code", "USA"),
        "congressional_district": pop.get("congressional_code", ""),
    }


def _extract_competition_info(data: dict[str, Any]) -> dict[str, Any]:
    """Extract competition and set-aside information."""
    return {
        "extent_competed": data.get("extent_competed") or data.get("Extent Competed", ""),
        "set_aside_type": data.get("set_aside_type") or data.get("Set Aside Type", ""),
        "pricing_type": data.get("pricing_type") or data.get("Pricing Type", ""),
        "number_of_offers": data.get("number_of_offers_received"),
        "is_sole_source": _is_sole_source(
            data.get("extent_competed") or data.get("Extent Competed", "")
        ),
    }


def _compute_risk_indicators(
    award_details: dict[str, Any],
    competition: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute basic risk indicators from parsed award data."""
    indicators = []

    # Sole-source indicator
    if competition.get("is_sole_source"):
        indicators.append({
            "type": "sole_source",
            "description": "Award was not competed (sole source)",
            "severity": "medium",
        })

    # High-value indicator
    amount = award_details.get("award_amount", 0) or 0
    if amount > 10_000_000:
        indicators.append({
            "type": "high_value",
            "description": f"Award value exceeds $10M: ${amount:,.2f}",
            "severity": "low",
        })

    # Cost-plus pricing indicator
    pricing = (award_details.get("pricing_type") or "").lower()
    if "cost" in pricing and "plus" in pricing:
        indicators.append({
            "type": "cost_plus_pricing",
            "description": "Cost-plus pricing type may warrant closer review",
            "severity": "low",
        })

    return indicators


def _collect_entity_mentions(data: dict[str, Any]) -> list[dict[str, str]]:
    """Collect all entity names found in the award data."""
    mentions = []

    # Recipient
    name = data.get("recipient_name") or data.get("Recipient Name", "")
    if name:
        mentions.append({"name": name, "type": "vendor", "role": "recipient"})

    # Awarding agency
    agency = data.get("awarding_agency") or data.get("Awarding Agency", "")
    if agency:
        mentions.append({"name": agency, "type": "government_agency", "role": "awarding_agency"})

    # Sub agency
    sub = data.get("awarding_sub_agency") or data.get("Awarding Sub Agency", "")
    if sub and sub != agency:
        mentions.append({"name": sub, "type": "government_agency", "role": "awarding_sub_agency"})

    return mentions


def _is_sole_source(extent_competed: str) -> bool:
    """Check if the extent competed indicates sole-source."""
    sole_source_codes = {
        "NOT COMPETED",
        "NOT AVAILABLE FOR COMPETITION",
        "SOLE SOURCE",
        "A",   # Not Available for Competition
        "B",   # Follow On to Competed Action
        "C",   # Not Competed
        "D",   # Not Competed - Unique Source
        "E",   # Follow On to Competed Action - Sole Source
        "CDO", # Competed under SAP
    }
    return (extent_competed or "").upper().strip() in sole_source_codes


def _safe_float(value: Any) -> float:
    """Safely convert a value to float."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
