"""DOJ press release parser.

Extracts structured entities from DOJ press release text:
- Named defendants (companies or individuals)
- Settlement amounts
- Case numbers and districts
- Relevant statutes (FCA, Anti-Kickback, etc.)
- Enforcement actions
"""

from __future__ import annotations

import re
from typing import Any


# Regex patterns
_AMOUNT_PATTERN = re.compile(
    r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(million|billion|thousand)?",
    re.IGNORECASE,
)
_CASE_NUMBER_PATTERN = re.compile(
    r"(?:Case\s+(?:No\.\s*)?|No\.\s+)(\d{1,2}[:-]\d{2}[:-](?:cv|cr|mc|mj|po)-\d+(?:-\w+)?)",
    re.IGNORECASE,
)
_DISTRICT_PATTERN = re.compile(
    r"((?:Eastern|Western|Northern|Southern|Central|Middle)\s+District\s+of\s+\w+(?:\s+\w+)?)",
    re.IGNORECASE,
)

# Statute patterns
_STATUTE_PATTERNS = {
    "false_claims_act": re.compile(r"False\s+Claims\s+Act", re.IGNORECASE),
    "anti_kickback": re.compile(
        r"Anti-?Kickback\s+(?:Statute|Act)", re.IGNORECASE
    ),
    "wire_fraud": re.compile(r"wire\s+fraud", re.IGNORECASE),
    "mail_fraud": re.compile(r"mail\s+fraud", re.IGNORECASE),
    "conspiracy": re.compile(r"conspiracy\s+to\s+(?:defraud|commit)", re.IGNORECASE),
    "trade_secrets": re.compile(
        r"(?:trade\s+secrets?|Economic\s+Espionage\s+Act)", re.IGNORECASE
    ),
    "bribery": re.compile(r"brib(?:ery|ing|e)", re.IGNORECASE),
    "money_laundering": re.compile(r"money\s+laundering", re.IGNORECASE),
    "bid_rigging": re.compile(r"bid\s+rig(?:ging|ged)", re.IGNORECASE),
    "qui_tam": re.compile(r"qui\s+tam", re.IGNORECASE),
}

# Enforcement action patterns
_ACTION_PATTERNS = {
    "civil_settlement": re.compile(
        r"(?:agreed?\s+to\s+pay|settle(?:ment|d)|resolved|paid)", re.IGNORECASE
    ),
    "criminal_conviction": re.compile(
        r"(?:convicted|pleaded?\s+guilty|guilty\s+plea|sentenced)", re.IGNORECASE
    ),
    "debarment": re.compile(
        r"(?:debar(?:red|ment)|suspend(?:ed|sion)|excluded)", re.IGNORECASE
    ),
    "indictment": re.compile(
        r"(?:indicted|charged|arraigned)", re.IGNORECASE
    ),
}


def parse_doj_press_release(data: dict[str, Any]) -> dict[str, Any]:
    """Parse a DOJ press release into normalized structured data.

    Args:
        data: Raw press release data from the DOJ connector or stored JSON.

    Returns:
        Normalized structure with entities, amounts, statutes, and actions.
    """
    title = data.get("title", "")
    body = data.get("body", "")
    full_text = f"{title}\n\n{body}"

    # Extract all structured fields
    amounts = _extract_amounts(full_text)
    case_numbers = _extract_case_numbers(full_text)
    districts = _extract_districts(full_text)
    statutes = _detect_statutes(full_text)
    actions = _detect_actions(full_text)
    entities = _collect_entity_mentions(data, full_text)

    return {
        "doc_type": "press_release",
        "source": "doj",
        "title": title,
        "date": data.get("date", ""),
        "component": data.get("component", ""),
        "topics": data.get("topic", []),
        "settlement_amounts": amounts,
        "case_numbers": case_numbers,
        "districts": districts,
        "statutes_cited": statutes,
        "enforcement_actions": actions,
        "entities_found": entities,
        "fraud_relevant": bool(statutes or actions),
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
        multiplier = multipliers.get(multiplier_text, 1)
        value *= multiplier

        amounts.append({
            "raw_text": match.group(0).strip(),
            "value_usd": value,
            "context": text[max(0, match.start() - 50) : match.end() + 50].strip(),
        })

    # Deduplicate and sort by value descending
    seen = set()
    unique_amounts = []
    for a in sorted(amounts, key=lambda x: x["value_usd"], reverse=True):
        if a["value_usd"] not in seen:
            seen.add(a["value_usd"])
            unique_amounts.append(a)
    return unique_amounts


def _extract_case_numbers(text: str) -> list[str]:
    """Extract federal case numbers from text."""
    return list(set(_CASE_NUMBER_PATTERN.findall(text)))


def _extract_districts(text: str) -> list[str]:
    """Extract federal district names from text."""
    return list(set(_DISTRICT_PATTERN.findall(text)))


def _detect_statutes(text: str) -> list[str]:
    """Detect which statutes are mentioned."""
    return [name for name, pattern in _STATUTE_PATTERNS.items() if pattern.search(text)]


def _detect_actions(text: str) -> list[str]:
    """Detect what enforcement actions are described."""
    return [name for name, pattern in _ACTION_PATTERNS.items() if pattern.search(text)]


def _sanitize_text(text: str) -> str:
    """Strip HTML tags and control characters from external text.

    Defends against prompt injection and XSS via upstream data.
    """
    # Remove HTML/script tags
    cleaned = re.sub(r"<[^>]+>", "", text)
    # Remove control characters except newlines/tabs
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    return cleaned.strip()


def _collect_entity_mentions(
    data: dict[str, Any], full_text: str
) -> list[dict[str, str]]:
    """Collect entity mentions from structured and unstructured data.

    Note: This is a heuristic extraction. For more accurate NER, the
    LLM-assisted extraction in the agentic pipeline will refine these.
    """
    mentions = []

    # From structured topic data
    for topic in data.get("topic", []):
        name = topic if isinstance(topic, str) else topic.get("name", "")
        if name and len(name) > 3:
            mentions.append({"name": _sanitize_text(name), "type": "topic", "role": "topic"})

    # Component as entity
    component = data.get("component", "")
    if component:
        mentions.append({
            "name": _sanitize_text(component),
            "type": "government_agency",
            "role": "doj_component",
        })

    # Simple heuristic: look for defendants in title patterns
    title = _sanitize_text(data.get("title", ""))
    # Pattern: "Company Name Agrees to Pay" or "Company Name Pleads Guilty"
    defendant_patterns = [
        re.compile(r"^(.+?)\s+(?:Agrees?|Pays?|Pleads?|Settles?|Convicted)", re.IGNORECASE),
        re.compile(r"^(.+?)\s+(?:and\s+.+?\s+)?(?:to\s+Pay|Charged|Indicted)", re.IGNORECASE),
    ]
    for pattern in defendant_patterns:
        match = pattern.match(title)
        if match:
            defendant = match.group(1).strip()
            if len(defendant) > 2 and len(defendant) < 200:
                mentions.append(
                    {"name": defendant, "type": "vendor", "role": "defendant"}
                )
            break

    return mentions
