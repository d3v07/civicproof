from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from typing import Any

import redis.asyncio as aioredis
from civicproof_common.db.models import EntityMentionModel, EntityModel
from civicproof_common.db.session import get_session
from civicproof_common.idempotency import IdempotencyGuard
from civicproof_common.schemas.events import EventEnvelope
from civicproof_common.telemetry import StructuredLogger

logger = StructuredLogger(__name__)
_stdlib_logger = logging.getLogger(__name__)

_CORP_SUFFIXES = re.compile(
    r"\b(inc|llc|llp|corp|corporation|incorporated|ltd|limited|co|company|"
    r"associates|group|holdings|enterprises|solutions|services|technologies|tech)\b\.?$",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_NON_ALPHANUM = re.compile(r"[^a-zA-Z0-9\s&,.\-]")
_UEI_PATTERN = re.compile(r"\b[A-Z0-9]{12}\b")
_CAGE_PATTERN = re.compile(r"\b[0-9A-Z]{5}\b")


def normalize_entity_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = _NON_ALPHANUM.sub(" ", ascii_name)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip().upper()
    return cleaned


def extract_identifiers(text: str) -> dict[str, list[str]]:
    ueis = _UEI_PATTERN.findall(text)
    cages = _CAGE_PATTERN.findall(text)
    return {
        "uei_candidates": list(set(ueis)),
        "cage_candidates": list(set(cages)),
    }


def extract_vendor_names(structured_data: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    name_fields = (
        "vendor_name",
        "awardee_name",
        "company_name",
        "registrant_name",
        "legal_name",
        "name",
        "recipient_name",
    )
    for field in name_fields:
        value = structured_data.get(field)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    recipient = structured_data.get("recipient", {})
    if isinstance(recipient, dict):
        for field in name_fields:
            value = recipient.get(field)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())

    return list(dict.fromkeys(candidates))


async def handle_normalize_requested(
    envelope: EventEnvelope,
    redis_client: aioredis.Redis,
) -> None:
    payload = envelope.payload
    artifact_id = payload.get("artifact_id", "")
    source = payload.get("source", "unknown")
    text_snippet = payload.get("text_snippet", "")
    structured_data = payload.get("structured_data", {})

    guard = IdempotencyGuard(redis_client)
    if not await guard.check_and_set(envelope.idempotency_key):
        logger.info(
            "normalize_duplicate",
            case_id=None,
            artifact_id=artifact_id,
            source=source,
            stage="normalize",
            policy_decision="deduplicated",
        )
        return

    vendor_names = extract_vendor_names(structured_data)
    identifiers = extract_identifiers(text_snippet)
    uei_candidates = identifiers["uei_candidates"]
    cage_candidates = identifiers["cage_candidates"]
    uei = structured_data.get("uei") or (uei_candidates[0] if uei_candidates else None)
    cage_code = (
        structured_data.get("cage_code")
        or (cage_candidates[0] if cage_candidates else None)
    )

    created_entities: list[str] = []

    async for db in get_session():
        from sqlalchemy import or_, select

        for raw_name in vendor_names:
            canonical = normalize_entity_name(raw_name)
            if not canonical:
                continue

            lookup = select(EntityModel).where(EntityModel.canonical_name == canonical)
            if uei:
                lookup = select(EntityModel).where(
                    or_(EntityModel.canonical_name == canonical, EntityModel.uei == uei)
                )

            result = await db.execute(lookup)
            entity = result.scalar_one_or_none()

            if entity is None:
                entity = EntityModel(
                    entity_id=str(uuid.uuid4()),
                    entity_type="vendor",
                    canonical_name=canonical,
                    aliases=[raw_name] if raw_name != canonical else [],
                    uei=uei,
                    cage_code=cage_code,
                    metadata_={"source": source, "artifact_id": artifact_id},
                )
                db.add(entity)
                await db.flush()
                created_entities.append(entity.entity_id)
            else:
                if raw_name not in (entity.aliases or []) and raw_name != entity.canonical_name:
                    entity.aliases = list(entity.aliases or []) + [raw_name]
                if uei and not entity.uei:
                    entity.uei = uei
                if cage_code and not entity.cage_code:
                    entity.cage_code = cage_code

            mention = EntityMentionModel(
                mention_id=str(uuid.uuid4()),
                source_artifact_id=artifact_id,
                resolved_entity_id=entity.entity_id,
                raw_text=raw_name[:500],
                offset_start=0,
                offset_end=len(raw_name),
            )
            db.add(mention)

        await db.commit()

    logger.info(
        "entities_normalized",
        case_id=None,
        artifact_id=artifact_id,
        source=source,
        stage="normalize",
        policy_decision="stored",
        entity_count=len(created_entities),
        vendor_names_found=len(vendor_names),
    )
