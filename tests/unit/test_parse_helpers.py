"""Unit tests for parse.py pure functions.

Tests _extract_text and _flatten_json_to_text — no async, no DB.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from src.handlers.parse import _extract_text, _flatten_json_to_text


class TestFlattenJsonToText:
    def test_flattens_string(self):
        parts: list[str] = []
        _flatten_json_to_text("hello world", parts)
        assert parts == ["hello world"]

    def test_flattens_dict(self):
        parts: list[str] = []
        _flatten_json_to_text({"a": "foo", "b": "bar"}, parts)
        assert "foo" in parts
        assert "bar" in parts

    def test_flattens_list(self):
        parts: list[str] = []
        _flatten_json_to_text(["one", "two"], parts)
        assert parts == ["one", "two"]

    def test_flattens_nested(self):
        parts: list[str] = []
        _flatten_json_to_text({"outer": {"inner": "value"}}, parts)
        assert "value" in parts

    def test_max_depth(self):
        # Build deeply nested structure
        obj: dict | str = "deep"
        for _ in range(12):
            obj = {"nested": obj}
        parts: list[str] = []
        _flatten_json_to_text(obj, parts)
        # Depth > 8 stops recursion, so "deep" should NOT appear
        assert "deep" not in parts

    def test_numbers_converted(self):
        parts: list[str] = []
        _flatten_json_to_text(42, parts)
        assert "42" in parts

    def test_none_skipped(self):
        parts: list[str] = []
        _flatten_json_to_text(None, parts)
        assert parts == []

    def test_empty_string_skipped(self):
        parts: list[str] = []
        _flatten_json_to_text("   ", parts)
        assert parts == []

    def test_boolean_converted(self):
        parts: list[str] = []
        _flatten_json_to_text(True, parts)
        assert "True" in parts


class TestExtractText:
    def test_plain_text(self):
        raw = b"Hello world"
        text, structured = _extract_text(raw, "unknown")
        assert text == "Hello world"
        assert structured == {}

    def test_json_contract_award(self):
        data = {"vendor_name": "Acme", "amount": 5000}
        raw = json.dumps(data).encode()
        text, structured = _extract_text(raw, "contract_award")
        assert structured["vendor_name"] == "Acme"
        assert "Acme" in text
        assert "5000" in text

    def test_json_autodetect(self):
        data = {"key": "value"}
        raw = json.dumps(data).encode()
        text, structured = _extract_text(raw, "other")
        assert structured["key"] == "value"

    def test_invalid_json_falls_back(self):
        raw = b"{invalid json}"
        text, structured = _extract_text(raw, "contract_award")
        assert text == "{invalid json}"
        assert structured == {}

    def test_json_list(self):
        data = [{"a": 1}, {"b": 2}]
        raw = json.dumps(data).encode()
        text, structured = _extract_text(raw, "contract_award")
        assert "items" in structured

    def test_truncates_to_1m_chars(self):
        raw = b"x" * 2_000_000
        text, structured = _extract_text(raw, "unknown")
        assert len(text) == 1_000_000

    def test_bad_encoding_handled(self):
        raw = b"\xff\xfe invalid utf8"
        text, structured = _extract_text(raw, "unknown")
        assert isinstance(text, str)

    def test_sam_registration_type(self):
        data = {"registrant_name": "Test Co", "uei": "ABC123DEF456"}
        raw = json.dumps(data).encode()
        text, structured = _extract_text(raw, "sam_registration")
        assert structured["registrant_name"] == "Test Co"

    def test_fec_filing_type(self):
        data = {"committee_name": "PAC Fund", "total": 10000}
        raw = json.dumps(data).encode()
        text, structured = _extract_text(raw, "fec_filing")
        assert structured["committee_name"] == "PAC Fund"

    def test_empty_bytes(self):
        text, structured = _extract_text(b"", "unknown")
        assert text == ""
        assert structured == {}
