"""Unit tests for GraphBuilderAgent helper methods and AnomalyDetectorAgent."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from src.agents.graph_builder import GraphBuilderAgent, GraphBuildResult  # noqa: E402


class TestSanitizeMentionText:
    def test_redacts_ssn(self):
        text = "Contact SSN 123-45-6789 for details"
        result = GraphBuilderAgent._sanitize_mention_text(text)
        assert "[SSN_REDACTED]" in result
        assert "123-45-6789" not in result

    def test_redacts_phone(self):
        text = "Call 555-123-4567 for info"
        result = GraphBuilderAgent._sanitize_mention_text(text)
        assert "[PHONE_REDACTED]" in result
        assert "555-123-4567" not in result

    def test_redacts_email(self):
        text = "Email john.doe@gmail.com for contact"
        result = GraphBuilderAgent._sanitize_mention_text(text)
        assert "[EMAIL_REDACTED]" in result
        assert "john.doe@gmail.com" not in result

    def test_preserves_non_pii(self):
        text = "ACME CORP <-> DEFENSE DEPT"
        result = GraphBuilderAgent._sanitize_mention_text(text)
        assert result == text

    def test_redacts_multiple_patterns(self):
        text = "SSN 123-45-6789, phone 555-111-2222, email test@yahoo.com"
        result = GraphBuilderAgent._sanitize_mention_text(text)
        assert "[SSN_REDACTED]" in result
        assert "[PHONE_REDACTED]" in result
        assert "[EMAIL_REDACTED]" in result

    def test_business_email_not_redacted(self):
        # Only personal email providers are redacted
        text = "Contact info@acmecorp.com"
        result = GraphBuilderAgent._sanitize_mention_text(text)
        assert "info@acmecorp.com" in result


class TestGeneratePairs:
    def _make_mention(self, entity_id, raw_text="mention"):
        m = MagicMock()
        m.resolved_entity_id = entity_id
        m.raw_text = raw_text
        return m

    def test_two_different_entities(self):
        mentions = [
            self._make_mention("e1", "ACME"),
            self._make_mention("e2", "DEFENSE DEPT"),
        ]
        pairs = GraphBuilderAgent._generate_pairs(mentions)
        assert len(pairs) == 1
        # Pair should be sorted
        assert pairs[0][0] < pairs[0][1] or pairs[0][0] == pairs[0][1]

    def test_same_entity_no_pair(self):
        mentions = [
            self._make_mention("e1", "ACME"),
            self._make_mention("e1", "ACME INC"),
        ]
        pairs = GraphBuilderAgent._generate_pairs(mentions)
        assert len(pairs) == 0

    def test_no_resolved_entity_skipped(self):
        mentions = [
            self._make_mention(None, "unknown"),
            self._make_mention("e1", "known"),
        ]
        pairs = GraphBuilderAgent._generate_pairs(mentions)
        assert len(pairs) == 0

    def test_deduplicates_pairs(self):
        mentions = [
            self._make_mention("e1", "A1"),
            self._make_mention("e2", "B1"),
            self._make_mention("e1", "A2"),
            self._make_mention("e2", "B2"),
        ]
        pairs = GraphBuilderAgent._generate_pairs(mentions)
        assert len(pairs) == 1  # Only one unique pair

    def test_three_entities_three_pairs(self):
        mentions = [
            self._make_mention("e1", "A"),
            self._make_mention("e2", "B"),
            self._make_mention("e3", "C"),
        ]
        pairs = GraphBuilderAgent._generate_pairs(mentions)
        assert len(pairs) == 3

    def test_empty_mentions(self):
        pairs = GraphBuilderAgent._generate_pairs([])
        assert pairs == []


class TestGraphBuildResult:
    def test_defaults(self):
        r = GraphBuildResult()
        assert r.edges_added == 0
        assert r.total_edges == 0
        assert r.centrality_scores == {}
        assert r.build_log == []
