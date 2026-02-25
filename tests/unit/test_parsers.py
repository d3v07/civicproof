"""Unit tests for source-specific parsers.

All parsers are pure functions — no mocking needed.
"""

import pytest

from parsers.usaspending import parse_usaspending_award
from parsers.doj import parse_doj_press_release
from parsers.sec_edgar import parse_sec_filing
from parsers.oversight import parse_ig_report


# ── USAspending Parser ─────────────────────────────────────────────


class TestUSAspendingParser:
    def test_basic_award(self):
        data = {
            "recipient_name": "Acme Corp",
            "recipient_uei": "ABC123XYZ789",
            "award_amount": 5_000_000,
            "awarding_agency": "Department of Defense",
            "extent_competed": "NOT COMPETED",
            "award_id": "CONT001",
        }
        result = parse_usaspending_award(data)
        assert result["doc_type"] == "contract_award"
        assert result["recipient"]["name"] == "Acme Corp"
        assert result["recipient"]["uei"] == "ABC123XYZ789"
        assert result["award_details"]["award_amount"] == 5_000_000

    def test_sole_source_risk_indicator(self):
        data = {
            "recipient_name": "Acme Corp",
            "extent_competed": "NOT COMPETED",
            "award_amount": 1_000,
        }
        result = parse_usaspending_award(data)
        risk_types = [r["type"] for r in result["risk_indicators"]]
        assert "sole_source" in risk_types

    def test_high_value_risk_indicator(self):
        data = {
            "recipient_name": "Acme Corp",
            "award_amount": 50_000_000,
            "extent_competed": "FULL AND OPEN",
        }
        result = parse_usaspending_award(data)
        risk_types = [r["type"] for r in result["risk_indicators"]]
        assert "high_value" in risk_types

    def test_entities_found(self):
        data = {
            "recipient_name": "Acme Corp",
            "awarding_agency": "DoD",
            "awarding_sub_agency": "DISA",
        }
        result = parse_usaspending_award(data)
        entity_names = [e["name"] for e in result["entities_found"]]
        assert "Acme Corp" in entity_names
        assert "DoD" in entity_names


# ── DOJ Parser ─────────────────────────────────────────────────────


class TestDOJParser:
    def test_amount_extraction(self):
        data = {
            "title": "Company Agrees to Pay $2.5 Million",
            "body": "The company agreed to pay $2.5 million to resolve False Claims Act allegations.",
        }
        result = parse_doj_press_release(data)
        assert len(result["settlement_amounts"]) >= 1
        assert result["settlement_amounts"][0]["value_usd"] == 2_500_000

    def test_statute_detection(self):
        data = {
            "title": "DOJ Announces Settlement",
            "body": "Resolved under the False Claims Act and the Anti-Kickback Statute.",
        }
        result = parse_doj_press_release(data)
        assert "false_claims_act" in result["statutes_cited"]
        assert "anti_kickback" in result["statutes_cited"]

    def test_enforcement_action_detection(self):
        data = {
            "title": "CEO Pleads Guilty",
            "body": "The defendant pleaded guilty to wire fraud charges.",
        }
        result = parse_doj_press_release(data)
        assert "criminal_conviction" in result["enforcement_actions"]
        assert "wire_fraud" in result["statutes_cited"]

    def test_fraud_relevance(self):
        data = {
            "title": "Weather Report",
            "body": "It will be sunny tomorrow.",
        }
        result = parse_doj_press_release(data)
        assert result["fraud_relevant"] is False

    def test_defendant_extraction_from_title(self):
        data = {
            "title": "Lockheed Martin Agrees to Pay $5 Million",
            "body": "Settlement details.",
        }
        result = parse_doj_press_release(data)
        entity_names = [e["name"] for e in result["entities_found"]]
        assert any("Lockheed Martin" in name for name in entity_names)


# ── SEC EDGAR Parser ──────────────────────────────────────────────


class TestSECEdgarParser:
    def test_basic_filing(self):
        data = {
            "entity_name": "Raytheon Technologies",
            "form_type": "10-K",
            "file_date": "2025-03-15",
            "cik": "0001234567",
        }
        result = parse_sec_filing(data)
        assert result["doc_type"] == "sec_filing"
        assert result["entity"]["name"] == "Raytheon Technologies"
        assert result["filing_details"]["form_type"] == "10-K"

    def test_gov_relevance_keywords(self):
        data = {
            "entity_name": "Defense Contractor Inc",
            "description": "government contract award for Department of Defense",
        }
        result = parse_sec_filing(data)
        assert result["gov_contract_relevance"]["is_relevant"] is True
        assert result["gov_contract_relevance"]["relevance_score"] > 0

    def test_irrelevant_filing(self):
        data = {
            "entity_name": "Coffee Shop LLC",
            "description": "Annual report for retail operations",
        }
        result = parse_sec_filing(data)
        assert result["gov_contract_relevance"]["is_relevant"] is False


# ── Oversight.gov Parser ──────────────────────────────────────────


class TestOversightParser:
    def test_basic_report(self):
        data = {
            "report_id": "r001",
            "title": "Audit of Procurement Fraud Controls",
            "agency": "DoD",
            "report_type": "Audit",
            "summary": "Found $3.2 million in waste.",
            "recommendations_count": 5,
        }
        result = parse_ig_report(data)
        assert result["doc_type"] == "ig_report"
        assert result["report"]["agency"] == "DoD"
        assert result["findings"]["recommendations_count"] == 5

    def test_procurement_relevance(self):
        data = {
            "title": "Investigation into Contract Fraud at Agency",
            "summary": "Procurement fraud and overbilling detected.",
        }
        result = parse_ig_report(data)
        assert result["procurement_relevance"]["is_relevant"] is True

    def test_amount_extraction(self):
        data = {
            "title": "Audit Report",
            "summary": "Identified $1.5 million in questioned costs.",
        }
        result = parse_ig_report(data)
        assert len(result["findings"]["extracted_amounts"]) >= 1
