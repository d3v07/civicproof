from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:acting\s+as|a\s+new)", re.IGNORECASE),
    re.compile(r"disregard\s+your\s+(?:previous\s+)?instructions?", re.IGNORECASE),
    re.compile(r"forget\s+everything\s+(?:you\s+know|above)", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"\{\{.*?\}\}", re.DOTALL),
    re.compile(r"prompt\s*injection", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
]

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){15,16}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


@dataclass
class FilterResult:
    allowed: bool
    sanitized_text: str
    blocked_reasons: list[str]
    pii_redacted: bool


def check_injection(text: str) -> list[str]:
    violations: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            violations.append(f"prompt_injection: matched pattern {pattern.pattern[:40]}")
    return violations


def redact_pii(text: str) -> tuple[str, bool]:
    changed = False
    result = text

    if _SSN_PATTERN.search(result):
        result = _SSN_PATTERN.sub("[SSN-REDACTED]", result)
        changed = True

    if _CREDIT_CARD_PATTERN.search(result):
        result = _CREDIT_CARD_PATTERN.sub("[CC-REDACTED]", result)
        changed = True

    if _EMAIL_PATTERN.search(result):
        result = _EMAIL_PATTERN.sub("[EMAIL-REDACTED]", result)
        changed = True

    return result, changed


class ContentFilter:
    def __init__(self, pii_redaction_enabled: bool = True) -> None:
        self._pii_redaction = pii_redaction_enabled

    def filter_input(self, text: str) -> FilterResult:
        violations = check_injection(text)
        if violations:
            logger.warning("prompt_injection_detected violations=%s", violations)
            return FilterResult(
                allowed=False,
                sanitized_text="",
                blocked_reasons=violations,
                pii_redacted=False,
            )

        sanitized = text
        pii_redacted = False
        if self._pii_redaction:
            sanitized, pii_redacted = redact_pii(sanitized)
            if pii_redacted:
                logger.info("pii_redacted from input")

        return FilterResult(
            allowed=True,
            sanitized_text=sanitized,
            blocked_reasons=[],
            pii_redacted=pii_redacted,
        )

    def filter_output(self, text: str) -> FilterResult:
        sanitized = text
        pii_redacted = False
        if self._pii_redaction:
            sanitized, pii_redacted = redact_pii(sanitized)

        return FilterResult(
            allowed=True,
            sanitized_text=sanitized,
            blocked_reasons=[],
            pii_redacted=pii_redacted,
        )
