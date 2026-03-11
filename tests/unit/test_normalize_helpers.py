"""Unit tests for normalize.py pure functions.

Tests normalize_entity_name, extract_identifiers, extract_vendor_names.
These are pure functions — no async, no DB, no mocking needed.
"""
from __future__ import annotations

import os
import sys

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from src.handlers.normalize import (  # noqa: E402
    extract_identifiers,
    extract_vendor_names,
    normalize_entity_name,
)


class TestNormalizeEntityName:
    def test_basic_uppercasing(self):
        assert normalize_entity_name("Acme Corp") == "ACME CORP"

    def test_strips_whitespace(self):
        assert normalize_entity_name("  Acme   Corp  ") == "ACME CORP"

    def test_unicode_normalization(self):
        # NFKD decomposes accented chars, then ascii ignore strips diacritics
        assert normalize_entity_name("Caf\u00e9 Corp") == "CAFE CORP"

    def test_removes_special_chars(self):
        assert normalize_entity_name("Acme! @Corp #123") == "ACME CORP 123"

    def test_preserves_ampersand_and_period(self):
        result = normalize_entity_name("AT&T Inc.")
        assert "&" in result
        assert "." in result

    def test_preserves_hyphen(self):
        result = normalize_entity_name("Rolls-Royce Holdings")
        assert "-" in result

    def test_empty_string(self):
        assert normalize_entity_name("") == ""

    def test_only_special_chars(self):
        assert normalize_entity_name("!!!") == ""

    def test_preserves_commas(self):
        result = normalize_entity_name("Lockheed Martin, Inc.")
        assert "," in result

    def test_multibyte_unicode(self):
        result = normalize_entity_name("\u00fc\u00f6\u00e4 GmbH")
        assert "GMBH" in result


class TestExtractIdentifiers:
    def test_finds_uei(self):
        text = "The entity UEI is ABC123DEF456 registered."
        result = extract_identifiers(text)
        assert "ABC123DEF456" in result["uei_candidates"]

    def test_finds_cage_code(self):
        text = "CAGE code: 1A2B3 for this vendor."
        result = extract_identifiers(text)
        assert "1A2B3" in result["cage_candidates"]

    def test_no_identifiers(self):
        result = extract_identifiers("no identifiers here")
        assert result["uei_candidates"] == []
        assert result["cage_candidates"] == []

    def test_deduplicates(self):
        text = "UEI ABC123DEF456 and again ABC123DEF456"
        result = extract_identifiers(text)
        assert len(result["uei_candidates"]) == 1

    def test_empty_string(self):
        result = extract_identifiers("")
        assert result["uei_candidates"] == []
        assert result["cage_candidates"] == []

    def test_multiple_ueis(self):
        text = "ABC123DEF456 and XYZ789QRS012"
        result = extract_identifiers(text)
        assert len(result["uei_candidates"]) == 2


class TestExtractVendorNames:
    def test_basic_vendor_name(self):
        data = {"vendor_name": "Acme Corp"}
        result = extract_vendor_names(data)
        assert "Acme Corp" in result

    def test_multiple_name_fields(self):
        data = {"vendor_name": "Acme Corp", "legal_name": "Acme Corporation"}
        result = extract_vendor_names(data)
        assert "Acme Corp" in result
        assert "Acme Corporation" in result

    def test_nested_recipient(self):
        data = {"recipient": {"name": "Nested Corp"}}
        result = extract_vendor_names(data)
        assert "Nested Corp" in result

    def test_deduplicates(self):
        data = {"vendor_name": "Acme", "name": "Acme"}
        result = extract_vendor_names(data)
        assert result.count("Acme") == 1

    def test_empty_dict(self):
        assert extract_vendor_names({}) == []

    def test_ignores_empty_strings(self):
        data = {"vendor_name": "", "name": "  "}
        assert extract_vendor_names(data) == []

    def test_ignores_non_string_values(self):
        data = {"vendor_name": 12345, "name": None}
        assert extract_vendor_names(data) == []

    def test_strips_whitespace(self):
        data = {"vendor_name": "  Acme Corp  "}
        result = extract_vendor_names(data)
        assert result[0] == "Acme Corp"

    def test_all_name_fields(self):
        data = {
            "vendor_name": "A",
            "awardee_name": "B",
            "company_name": "C",
            "registrant_name": "D",
            "legal_name": "E",
            "name": "F",
            "recipient_name": "G",
        }
        result = extract_vendor_names(data)
        assert len(result) == 7

    def test_recipient_is_not_dict(self):
        data = {"recipient": "not a dict", "vendor_name": "OK"}
        result = extract_vendor_names(data)
        assert "OK" in result
