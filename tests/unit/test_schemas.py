from __future__ import annotations

import uuid

import pytest
from civicproof_common.schemas.artifacts import DataSource, DocType, ParsedDoc, RawArtifact
from civicproof_common.schemas.cases import (
    AuditEvent,
    Case,
    CasePack,
    CaseStatus,
    Citation,
    Claim,
    ClaimType,
)
from civicproof_common.schemas.entities import (
    Entity,
    EntityMention,
    EntityType,
    Relationship,
    RelationshipType,
)
from civicproof_common.schemas.events import EventEnvelope, EventType


class TestEventEnvelope:
    def test_build_creates_valid_envelope(self):
        envelope = EventEnvelope.build(
            event_type=EventType.ARTIFACT_INGESTED,
            source="test_source",
            payload={"artifact_id": "abc123"},
            idempotency_key="idem-001",
        )
        assert envelope.event_type == EventType.ARTIFACT_INGESTED
        assert envelope.source == "test_source"
        assert envelope.payload["artifact_id"] == "abc123"
        assert envelope.idempotency_key == "idem-001"
        assert len(envelope.event_id) == 36

    def test_auto_generates_event_id(self):
        e1 = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="s",
            payload={},
            idempotency_key="k1",
        )
        e2 = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="s",
            payload={},
            idempotency_key="k2",
        )
        assert e1.event_id != e2.event_id

    def test_timestamp_is_utc(self):
        envelope = EventEnvelope.build(
            event_type=EventType.ENTITY_RESOLVED,
            source="s",
            payload={},
            idempotency_key="k",
        )
        assert envelope.timestamp.tzinfo is not None

    def test_serialization_round_trip(self):
        envelope = EventEnvelope.build(
            event_type=EventType.CLAIM_AUDITED,
            source="auditor",
            payload={"claim_id": "c123", "passed": True},
            idempotency_key="audit-001",
        )
        json_str = envelope.model_dump_json()
        restored = EventEnvelope.model_validate_json(json_str)
        assert restored.event_type == envelope.event_type
        assert restored.idempotency_key == envelope.idempotency_key
        assert restored.payload["claim_id"] == "c123"

    def test_empty_idempotency_key_raises(self):
        with pytest.raises(ValueError):
            EventEnvelope(
                event_type=EventType.ARTIFACT_INGESTED,
                source="s",
                payload={},
                idempotency_key="  ",
            )

    def test_all_event_types(self):
        for event_type in EventType:
            e = EventEnvelope.build(
                event_type=event_type,
                source="test",
                payload={},
                idempotency_key=str(uuid.uuid4()),
            )
            assert e.event_type == event_type


class TestEntitySchemas:
    def test_entity_defaults(self):
        entity = Entity(
            entity_type=EntityType.VENDOR,
            canonical_name="APEX SOLUTIONS LLC",
        )
        assert entity.entity_id is not None
        assert entity.uei is None
        assert entity.aliases == []
        assert entity.metadata == {}

    def test_entity_with_all_fields(self):
        entity = Entity(
            entity_type=EntityType.VENDOR,
            canonical_name="APEX SOLUTIONS LLC",
            aliases=["Apex Solutions", "Apex LLC"],
            uei="ABCDEF123456",
            cage_code="1AB2C",
            duns="123456789",
            metadata={"source": "usaspending"},
        )
        assert entity.uei == "ABCDEF123456"
        assert len(entity.aliases) == 2

    def test_relationship_confidence_bounds(self):
        with pytest.raises(ValueError):
            Relationship(
                source_entity_id="a",
                target_entity_id="b",
                rel_type=RelationshipType.OWNS,
                confidence=1.5,
            )
        with pytest.raises(ValueError):
            Relationship(
                source_entity_id="a",
                target_entity_id="b",
                rel_type=RelationshipType.OWNS,
                confidence=-0.1,
            )

    def test_valid_relationship(self):
        rel = Relationship(
            source_entity_id=str(uuid.uuid4()),
            target_entity_id=str(uuid.uuid4()),
            rel_type=RelationshipType.SUBSIDIARY_OF,
            evidence_ids=["art-001"],
            confidence=0.85,
        )
        assert rel.confidence == 0.85
        assert rel.rel_type == RelationshipType.SUBSIDIARY_OF

    def test_entity_mention(self):
        mention = EntityMention(
            raw_text="Apex Solutions LLC",
            source_artifact_id=str(uuid.uuid4()),
            offset_start=0,
            offset_end=18,
        )
        assert mention.resolved_entity_id is None
        assert mention.offset_end == 18


class TestCaseSchemas:
    def test_case_defaults(self):
        case = Case(
            title="Investigation: Vendor XYZ",
            seed_input={"vendor_name": "XYZ Corp"},
        )
        assert case.status == CaseStatus.PENDING
        assert case.case_id is not None
        assert case.created_at is not None

    def test_case_status_transitions(self):
        for status in CaseStatus:
            case = Case(
                title="Test",
                seed_input={},
                status=status,
            )
            assert case.status == status

    def test_claim_confidence_bounds(self):
        with pytest.raises(ValueError):
            Claim(case_id="c1", statement="test", claim_type=ClaimType.RISK_SIGNAL, confidence=1.5)
        claim = Claim(
            case_id="c1",
            statement="Vendor received 95% of awards",
            claim_type=ClaimType.RISK_SIGNAL,
            confidence=0.9,
        )
        assert claim.confidence == 0.9

    def test_citation_creation(self):
        citation = Citation(
            claim_id=str(uuid.uuid4()),
            artifact_id=str(uuid.uuid4()),
            excerpt="Award amount: $5,000,000",
            page_ref="p.12",
        )
        assert citation.citation_id is not None

    def test_case_pack_serialization(self):
        claim = Claim(
            case_id="c1",
            statement="Risk signal detected",
            claim_type=ClaimType.RISK_SIGNAL,
            confidence=0.7,
        )
        citation = Citation(
            claim_id=claim.claim_id,
            artifact_id="art-001",
            excerpt="Contract value inflated",
        )
        audit = AuditEvent(
            case_id="c1",
            stage="auditor",
            policy_decision="approved",
            detail="All claims grounded",
        )
        pack = CasePack(
            case_id="c1",
            claims=[claim],
            citations=[citation],
            audit_events=[audit],
        )
        as_dict = pack.model_dump()
        assert as_dict["case_id"] == "c1"
        assert len(as_dict["claims"]) == 1
        assert len(as_dict["citations"]) == 1
        assert len(as_dict["audit_events"]) == 1


class TestArtifactSchemas:
    def test_raw_artifact_creation(self):
        artifact = RawArtifact(
            source=DataSource.USASPENDING,
            source_url="https://api.usaspending.gov/awards/123",
            content_hash="a" * 64,
            storage_path="artifacts/aa/aaa...raw",
        )
        assert artifact.artifact_id is not None
        assert artifact.metadata == {}

    def test_parsed_doc_creation(self):
        doc = ParsedDoc(
            artifact_id=str(uuid.uuid4()),
            doc_type=DocType.CONTRACT_AWARD,
            extracted_text="Contract awarded to Apex Solutions LLC",
            structured_data={"amount": 500000},
        )
        assert doc.doc_id is not None
        assert doc.parsed_at is not None

    def test_all_data_sources(self):
        for source in DataSource:
            artifact = RawArtifact(
                source=source,
                source_url="https://example.com",
                content_hash="b" * 64,
                storage_path="artifacts/test",
            )
            assert artifact.source == source
