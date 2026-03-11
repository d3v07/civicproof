"""Evidence Retrieval Agent.

Checks existing artifacts in the evidence store for a resolved entity,
identifies gaps in coverage across data sources, and triggers fresh
fetches for stale or missing data via connector calls.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from civicproof_common.config import get_settings
from civicproof_common.db.models import RawArtifactModel
from civicproof_common.hashing import content_hash
from civicproof_common.rate_limiter import RateLimiter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.doj import DOJConnector
from ..connectors.oversight import OversightGovConnector
from ..connectors.sec_edgar import SECEdgarConnector
from ..connectors.usaspending import USAspendingConnector

logger = logging.getLogger(__name__)

# Maximum artifact age before triggering a refresh
STALENESS_THRESHOLD = timedelta(days=30)

# Expected data sources for a complete investigation
EXPECTED_SOURCES = ["usaspending", "doj", "sec_edgar", "oversight_gov", "sam_gov", "openfec"]


@dataclass
class ArtifactManifest:
    """Summary of artifacts available for an entity."""

    entity_id: str
    total_artifacts: int = 0
    artifacts_by_source: dict[str, int] = field(default_factory=dict)
    stale_sources: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    freshness: dict[str, datetime | None] = field(default_factory=dict)
    coverage_score: float = 0.0


@dataclass
class EvidenceRetrievalResult:
    """Result from the evidence retrieval agent."""

    manifest: ArtifactManifest
    fetches_triggered: list[dict[str, Any]] = field(default_factory=list)
    retrieval_log: list[dict[str, Any]] = field(default_factory=list)


class EvidenceRetrievalAgent:
    """Retrieves and audits evidence availability for a case entity.

    This agent is READ-only — it inspects the artifact store but
    cannot delete or modify existing artifacts (tool scoping).
    """

    def __init__(
        self,
        db: AsyncSession,
        staleness_threshold: timedelta = STALENESS_THRESHOLD,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._db = db
        self._staleness = staleness_threshold
        self._rate_limiter = rate_limiter

    async def retrieve(
        self,
        entity_id: str,
        entity_name: str,
        entity_uei: str | None = None,
    ) -> EvidenceRetrievalResult:
        """Check existing artifacts and identify gaps.

        Args:
            entity_id: The resolved entity ID.
            entity_name: Canonical entity name for searching.
            entity_uei: Optional UEI for narrower search.

        Returns:
            EvidenceRetrievalResult with manifest and gap analysis.
        """
        manifest = ArtifactManifest(entity_id=entity_id)

        # Query existing artifacts related to this entity
        artifacts = await self._query_artifacts(entity_name, entity_uei)

        # Build manifest
        for art in artifacts:
            source = art.source
            manifest.total_artifacts += 1
            manifest.artifacts_by_source[source] = (
                manifest.artifacts_by_source.get(source, 0) + 1
            )
            manifest.artifact_ids.append(art.artifact_id)

            # Track freshness
            if source not in manifest.freshness or (
                art.retrieved_at
                and (
                    manifest.freshness[source] is None
                    or art.retrieved_at > manifest.freshness[source]  # type: ignore[operator]
                )
            ):
                manifest.freshness[source] = art.retrieved_at

        # Identify stale and missing sources
        now = datetime.now(UTC)
        for source in EXPECTED_SOURCES:
            if source not in manifest.artifacts_by_source:
                manifest.missing_sources.append(source)
            elif manifest.freshness.get(source) is not None:
                age = now - manifest.freshness[source]  # type: ignore[operator]
                if age > self._staleness:
                    manifest.stale_sources.append(source)

        # Compute coverage score (0.0 - 1.0)
        covered = len(manifest.artifacts_by_source)
        expected = len(EXPECTED_SOURCES)
        staleness_penalty = len(manifest.stale_sources) * 0.1
        manifest.coverage_score = max(
            0.0, (covered / expected) - staleness_penalty
        )

        result = EvidenceRetrievalResult(manifest=manifest)

        # Log gaps
        if manifest.missing_sources:
            result.retrieval_log.append({
                "action": "gap_identified",
                "missing_sources": manifest.missing_sources,
                "entity": entity_name,
            })

        if manifest.stale_sources:
            result.retrieval_log.append({
                "action": "staleness_detected",
                "stale_sources": manifest.stale_sources,
                "threshold_days": self._staleness.days,
            })

        # Fetch from each source if missing or stale
        sources_to_fetch = set(manifest.missing_sources + manifest.stale_sources)
        fetched_any = False

        if "usaspending" in sources_to_fetch:
            if await self._fetch_usaspending(entity_name, result):
                fetched_any = True

        if "sec_edgar" in sources_to_fetch:
            if await self._fetch_sec_edgar(entity_name, result):
                fetched_any = True

        if "doj" in sources_to_fetch:
            if await self._fetch_doj(entity_name, result):
                fetched_any = True

        if "oversight_gov" in sources_to_fetch:
            if await self._fetch_oversight(entity_name, result):
                fetched_any = True

        if "sam_gov" in sources_to_fetch:
            if await self._fetch_sam_gov(entity_name, result):
                fetched_any = True

        if "openfec" in sources_to_fetch:
            if await self._fetch_openfec(entity_name, result):
                fetched_any = True

        if fetched_any:
            refreshed = await self._query_artifacts(entity_name, entity_uei)
            manifest.artifact_ids = [a.artifact_id for a in refreshed]
            manifest.total_artifacts = len(refreshed)
            manifest.artifacts_by_source = {}
            for a in refreshed:
                manifest.artifacts_by_source[a.source] = (
                    manifest.artifacts_by_source.get(a.source, 0) + 1
                )
            # Update missing/stale lists
            manifest.missing_sources = [
                s for s in EXPECTED_SOURCES if s not in manifest.artifacts_by_source
            ]
            manifest.stale_sources = []
            now = datetime.now(UTC)
            for source in manifest.artifacts_by_source:
                ts = manifest.freshness.get(source)
                if ts and (now - ts) > self._staleness:
                    manifest.stale_sources.append(source)
            manifest.coverage_score = max(
                0.0, len(manifest.artifacts_by_source) / len(EXPECTED_SOURCES)
                - len(manifest.stale_sources) * 0.1
            )

        return result

    async def _upsert_artifact(
        self, source: str, canonical_url: str, c_hash: str, raw_data: dict,
    ) -> bool:
        """Insert artifact, skip if duplicate (source, content_hash). Returns True if new."""
        stmt = pg_insert(RawArtifactModel).values(
            artifact_id=str(uuid.uuid4()),
            source=source,
            source_url=canonical_url,
            content_hash=c_hash,
            storage_path=f"artifacts/{source}/{c_hash[:16]}.json",
            metadata_=raw_data,
        ).on_conflict_do_nothing(index_elements=["source", "content_hash"])
        r = await self._db.execute(stmt)
        return r.rowcount > 0

    async def _fetch_usaspending(
        self, entity_name: str, result: EvidenceRetrievalResult,
    ) -> int:
        """Fetch awards from USAspending and store as raw artifacts."""
        connector = USAspendingConnector(rate_limiter=self._rate_limiter)
        stored = 0
        try:
            records = await connector.search_by_recipient_name(entity_name, max_pages=2)
            for record in records:
                raw_bytes = json.dumps(record, sort_keys=True, default=str).encode()
                c_hash = content_hash(raw_bytes)
                canonical_url = connector.canonical_url(record)
                if await self._upsert_artifact("usaspending", canonical_url, c_hash, record):
                    stored += 1
            result.fetches_triggered.append({
                "source": "usaspending",
                "records_fetched": len(records),
                "records_stored": stored,
            })
            logger.info("usaspending fetch entity=%s stored=%d", entity_name, stored)
        except Exception as exc:
            logger.warning("usaspending fetch failed for %s: %s", entity_name, exc)
            result.retrieval_log.append({
                "action": "fetch_failed",
                "source": "usaspending",
                "error": str(exc),
            })
        finally:
            await connector.close()
        return stored

    async def _fetch_sec_edgar(
        self, entity_name: str, result: EvidenceRetrievalResult,
    ) -> int:
        """Fetch SEC EDGAR filings and store as raw artifacts."""
        connector = SECEdgarConnector(rate_limiter=self._rate_limiter)
        stored = 0
        try:
            records = await connector.search_company_filings(entity_name, max_pages=2)
            for record in records:
                raw_bytes = json.dumps(record, sort_keys=True, default=str).encode()
                c_hash = content_hash(raw_bytes)
                canonical_url = connector.canonical_url(record)
                if await self._upsert_artifact("sec_edgar", canonical_url, c_hash, record):
                    stored += 1
            result.fetches_triggered.append({
                "source": "sec_edgar",
                "records_fetched": len(records),
                "records_stored": stored,
            })
            logger.info("sec_edgar fetch entity=%s stored=%d", entity_name, stored)
        except Exception as exc:
            logger.warning("sec_edgar fetch failed for %s: %s", entity_name, exc)
            result.retrieval_log.append({
                "action": "fetch_failed", "source": "sec_edgar", "error": str(exc),
            })
        finally:
            await connector.close()
        return stored

    async def _fetch_doj(
        self, entity_name: str, result: EvidenceRetrievalResult,
    ) -> int:
        """Fetch DOJ press releases mentioning entity and store as raw artifacts."""
        connector = DOJConnector(rate_limiter=self._rate_limiter)
        stored = 0
        try:
            records = await connector.search_fraud_releases(max_pages=2)
            # Filter to only fraud-relevant releases that mention the entity
            entity_lower = entity_name.lower()
            relevant = [
                r for r in records
                if entity_lower in (r.get("title", "") + r.get("body", "")).lower()
            ]
            for record in relevant:
                raw_bytes = json.dumps(record, sort_keys=True, default=str).encode()
                c_hash = content_hash(raw_bytes)
                canonical_url = connector.canonical_url(record)
                if await self._upsert_artifact("doj", canonical_url, c_hash, record):
                    stored += 1
            result.fetches_triggered.append({
                "source": "doj",
                "records_fetched": len(records),
                "records_relevant": len(relevant),
                "records_stored": stored,
            })
            logger.info(
                "doj fetch entity=%s relevant=%d stored=%d",
                entity_name, len(relevant), stored,
            )
        except Exception as exc:
            logger.warning("doj fetch failed for %s: %s", entity_name, exc)
            result.retrieval_log.append({
                "action": "fetch_failed", "source": "doj", "error": str(exc),
            })
        finally:
            await connector.close()
        return stored

    async def _fetch_oversight(
        self, entity_name: str, result: EvidenceRetrievalResult,
    ) -> int:
        """Fetch Oversight.gov IG reports mentioning entity."""
        connector = OversightGovConnector(rate_limiter=self._rate_limiter)
        stored = 0
        try:
            records = await connector.search_ig_reports(entity_name, max_pages=2)
            for record in records:
                raw_bytes = json.dumps(record, sort_keys=True, default=str).encode()
                c_hash = content_hash(raw_bytes)
                canonical_url = connector.canonical_url(record)
                if await self._upsert_artifact("oversight_gov", canonical_url, c_hash, record):
                    stored += 1
            result.fetches_triggered.append({
                "source": "oversight_gov",
                "records_fetched": len(records),
                "records_stored": stored,
            })
            logger.info("oversight_gov fetch entity=%s stored=%d", entity_name, stored)
        except Exception as exc:
            logger.warning("oversight_gov fetch failed for %s: %s", entity_name, exc)
            result.retrieval_log.append({
                "action": "fetch_failed", "source": "oversight_gov", "error": str(exc),
            })
        finally:
            await connector.close()
        return stored

    async def _fetch_sam_gov(
        self, entity_name: str, result: EvidenceRetrievalResult,
    ) -> int:
        """Fetch SAM.gov contract opportunities mentioning entity."""
        settings = get_settings()
        if not settings.SAM_GOV_API_KEY:
            result.retrieval_log.append({
                "action": "skipped", "source": "sam_gov", "reason": "no_api_key",
            })
            return 0
        from ..connectors.sam_gov import SAMGovConnector
        connector = SAMGovConnector(
            api_key=settings.SAM_GOV_API_KEY, rate_limiter=self._rate_limiter,
        )
        stored = 0
        try:
            from ..connectors.base import FetchParams
            fetch_result = await connector.fetch_page(FetchParams(
                query={"keyword": entity_name}, page_size=50,
            ))
            for record in fetch_result.artifacts:
                raw_bytes = json.dumps(record, sort_keys=True, default=str).encode()
                c_hash = content_hash(raw_bytes)
                canonical_url = connector.canonical_url(record)
                if await self._upsert_artifact("sam_gov", canonical_url, c_hash, record):
                    stored += 1
            result.fetches_triggered.append({
                "source": "sam_gov",
                "records_fetched": len(fetch_result.artifacts),
                "records_stored": stored,
            })
            logger.info("sam_gov fetch entity=%s stored=%d", entity_name, stored)
        except Exception as exc:
            logger.warning("sam_gov fetch failed for %s: %s", entity_name, exc)
            result.retrieval_log.append({
                "action": "fetch_failed", "source": "sam_gov", "error": str(exc),
            })
        finally:
            await connector.close()
        return stored

    async def _fetch_openfec(
        self, entity_name: str, result: EvidenceRetrievalResult,
    ) -> int:
        """Fetch OpenFEC contributions by employer matching entity."""
        settings = get_settings()
        if not settings.OPENFEC_API_KEY:
            result.retrieval_log.append({
                "action": "skipped", "source": "openfec", "reason": "no_api_key",
            })
            return 0
        from ..connectors.openfec import OpenFECConnector
        connector = OpenFECConnector(
            api_key=settings.OPENFEC_API_KEY, rate_limiter=self._rate_limiter,
        )
        stored = 0
        try:
            from ..connectors.base import FetchParams
            fetch_result = await connector.fetch_page(FetchParams(
                query={"endpoint": "schedules/schedule_a", "employer": entity_name},
                page_size=50,
            ))
            for record in fetch_result.artifacts:
                raw_bytes = json.dumps(record, sort_keys=True, default=str).encode()
                c_hash = content_hash(raw_bytes)
                canonical_url = connector.canonical_url(record)
                if await self._upsert_artifact("openfec", canonical_url, c_hash, record):
                    stored += 1
            result.fetches_triggered.append({
                "source": "openfec",
                "records_fetched": len(fetch_result.artifacts),
                "records_stored": stored,
            })
            logger.info("openfec fetch entity=%s stored=%d", entity_name, stored)
        except Exception as exc:
            logger.warning("openfec fetch failed for %s: %s", entity_name, exc)
            result.retrieval_log.append({
                "action": "fetch_failed", "source": "openfec", "error": str(exc),
            })
        finally:
            await connector.close()
        return stored

    async def _query_artifacts(
        self, entity_name: str, entity_uei: str | None = None,
    ) -> list[RawArtifactModel]:
        """Query artifacts related to an entity by name or UEI."""
        from sqlalchemy import cast, or_
        from sqlalchemy.types import Text

        conditions = []

        if entity_name:
            name_lower = entity_name.lower()
            conditions.append(
                RawArtifactModel.source_url.ilike(f"%{name_lower}%")
            )
            # Also search inside JSONB metadata (recipient_name etc.)
            conditions.append(
                cast(RawArtifactModel.metadata_, Text).ilike(f"%{name_lower}%")
            )

        if not conditions:
            return []

        stmt = (
            select(RawArtifactModel)
            .where(or_(*conditions))
            .order_by(RawArtifactModel.retrieved_at.desc())
            .limit(500)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars())
