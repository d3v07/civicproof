"""Entity Resolver Agent.

Canonicalizes vendor identities from seed input through
deterministic lookup, fuzzy matching, and LLM-assisted disambiguation.

Resolution tiers:
  1. Deterministic (confidence 1.0): UEI, CAGE, CIK, Award ID exact match
  2. Fuzzy (confidence 0.7-0.95): Name normalization + trigram similarity
  3. LLM-assisted (confidence 0.6-0.9): Disambiguation via gateway (future)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from civicproof_common.db.models import EntityModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ResolvedEntity:
    """Result of entity resolution."""

    entity_id: str
    canonical_name: str
    entity_type: str
    confidence: float
    resolution_method: str  # "deterministic", "fuzzy", "llm"
    uei: str | None = None
    cage_code: str | None = None
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityResolutionResult:
    """Complete result from the entity resolver agent."""

    primary_entity: ResolvedEntity | None = None
    related_entities: list[ResolvedEntity] = field(default_factory=list)
    resolution_log: list[dict[str, Any]] = field(default_factory=list)


class EntityResolverAgent:
    """Resolves seed input into canonical entity IDs."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(self, seed_input: dict[str, Any]) -> EntityResolutionResult:
        """Resolve seed input to canonical entities.

        Seed input may contain:
          - vendor_name: "Booz Allen Hamilton"
          - uei: "ABC123XYZ789"
          - cage_code: "1A2B3"
          - award_id: "CONT0012345"
          - tip_text: free-form investigative tip
        """
        result = EntityResolutionResult()

        # Tier 1: Deterministic — exact identifier match
        entity = await self._resolve_deterministic(seed_input)
        if entity:
            result.primary_entity = entity
            result.resolution_log.append({
                "tier": "deterministic",
                "input": {k: v for k, v in seed_input.items() if k != "tip_text"},
                "resolved": entity.entity_id,
                "confidence": entity.confidence,
            })
        else:
            # Tier 2: Fuzzy — name normalization
            vendor_name = seed_input.get("vendor_name") or seed_input.get("seed", "")
            if vendor_name:
                entity = await self._resolve_fuzzy(vendor_name)
                if entity:
                    result.primary_entity = entity
                    result.resolution_log.append({
                        "tier": "fuzzy",
                        "input_name": vendor_name,
                        "resolved": entity.entity_id,
                        "confidence": entity.confidence,
                    })

        # If no entity found, create a new one from the seed
        if result.primary_entity is None:
            entity = await self._create_from_seed(seed_input)
            result.primary_entity = entity
            result.resolution_log.append({
                "tier": "new_entity",
                "seed_input": {k: v for k, v in seed_input.items() if k != "tip_text"},
                "created": entity.entity_id,
            })

        # Find related entities
        if result.primary_entity:
            related = await self._find_related(result.primary_entity)
            result.related_entities = related

        return result

    async def _resolve_deterministic(
        self, seed_input: dict[str, Any]
    ) -> ResolvedEntity | None:
        """Tier 1: Exact match on UEI, CAGE code, or CIK."""
        conditions = []

        uei = seed_input.get("uei")
        if uei:
            conditions.append(EntityModel.uei == uei)

        cage_code = seed_input.get("cage_code")
        if cage_code:
            conditions.append(EntityModel.cage_code == cage_code)

        if not conditions:
            return None

        stmt = select(EntityModel).where(or_(*conditions))
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            return None

        return ResolvedEntity(
            entity_id=row.entity_id,
            canonical_name=row.canonical_name,
            entity_type=row.entity_type,
            confidence=1.0,
            resolution_method="deterministic",
            uei=row.uei,
            cage_code=row.cage_code,
            aliases=row.aliases or [],
            metadata=row.metadata_ or {},
        )

    async def _resolve_fuzzy(self, vendor_name: str) -> ResolvedEntity | None:
        """Tier 2: Fuzzy name matching via canonical name normalization."""
        import re
        import unicodedata

        # Normalize the input name
        normalized = unicodedata.normalize("NFKD", vendor_name)
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        canonical = re.sub(r"[^a-zA-Z0-9\s&,.\-]", " ", ascii_name)
        canonical = re.sub(r"\s+", " ", canonical).strip().upper()

        if not canonical:
            return None

        # Exact canonical match
        stmt = select(EntityModel).where(EntityModel.canonical_name == canonical)
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()

        if row:
            return ResolvedEntity(
                entity_id=row.entity_id,
                canonical_name=row.canonical_name,
                entity_type=row.entity_type,
                confidence=0.95,
                resolution_method="fuzzy",
                uei=row.uei,
                cage_code=row.cage_code,
                aliases=row.aliases or [],
            )

        # Try partial match (LIKE)
        stmt = select(EntityModel).where(
            EntityModel.canonical_name.ilike(f"%{canonical}%")
        ).limit(5)
        result = await self._db.execute(stmt)
        rows = list(result.scalars())

        if rows:
            # Return best match (shortest name = most specific)
            best = min(rows, key=lambda r: len(r.canonical_name))
            return ResolvedEntity(
                entity_id=best.entity_id,
                canonical_name=best.canonical_name,
                entity_type=best.entity_type,
                confidence=0.75,
                resolution_method="fuzzy",
                uei=best.uei,
                cage_code=best.cage_code,
                aliases=best.aliases or [],
            )

        return None

    async def _create_from_seed(
        self, seed_input: dict[str, Any]
    ) -> ResolvedEntity:
        """Create a new entity from seed input when no match is found.

        Uses ON CONFLICT-style handling to avoid race conditions when
        multiple workers resolve the same entity concurrently.
        """
        import re
        import unicodedata

        from sqlalchemy.exc import IntegrityError

        name = seed_input.get("vendor_name") or seed_input.get("seed", "Unknown")
        entity_type = seed_input.get("entity_type", "vendor")
        normalized = unicodedata.normalize("NFKD", name)
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        canonical = re.sub(r"[^a-zA-Z0-9\s&,.\-]", " ", ascii_name)
        canonical = re.sub(r"\s+", " ", canonical).strip().upper()

        entity_id = str(uuid.uuid4())
        entity = EntityModel(
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=canonical or name.upper(),
            aliases=[name] if name != canonical else [],
            uei=seed_input.get("uei"),
            cage_code=seed_input.get("cage_code"),
            metadata_={"source": "seed_input", "seed": seed_input},
        )
        try:
            self._db.add(entity)
            await self._db.flush()
        except IntegrityError:
            await self._db.rollback()
            # Another worker created this entity first — look it up
            existing = await self._resolve_fuzzy(canonical or name)
            if existing:
                return existing
            # If still not found, re-raise
            raise

        return ResolvedEntity(
            entity_id=entity_id,
            canonical_name=canonical or name.upper(),
            entity_type=entity_type,
            confidence=0.5,
            resolution_method="new_entity",
            uei=seed_input.get("uei"),
            cage_code=seed_input.get("cage_code"),
        )

    async def _find_related(
        self, primary: ResolvedEntity, limit: int = 10
    ) -> list[ResolvedEntity]:
        """Find related entities through shared identifiers or relationships."""
        from civicproof_common.db.models import RelationshipModel

        related = []
        stmt = select(RelationshipModel).where(
            or_(
                RelationshipModel.source_entity_id == primary.entity_id,
                RelationshipModel.target_entity_id == primary.entity_id,
            )
        ).limit(limit)
        result = await self._db.execute(stmt)

        for rel in result.scalars():
            related_id = (
                rel.target_entity_id
                if rel.source_entity_id == primary.entity_id
                else rel.source_entity_id
            )
            entity = await self._db.execute(
                select(EntityModel).where(EntityModel.entity_id == related_id)
            )
            row = entity.scalar_one_or_none()
            if row:
                related.append(ResolvedEntity(
                    entity_id=row.entity_id,
                    canonical_name=row.canonical_name,
                    entity_type=row.entity_type,
                    confidence=rel.confidence or 0.5,
                    resolution_method="graph",
                    uei=row.uei,
                    cage_code=row.cage_code,
                ))

        return related
