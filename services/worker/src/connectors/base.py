"""Base connector ABC and shared data structures for all source connectors."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx
from civicproof_common.hashing import content_hash
from civicproof_common.rate_limiter import RateLimiter

USER_AGENT = "CivicProof/0.1 (+https://github.com/d3v07/civicproof)"

# Timeout defaults (seconds)
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 30


@dataclass
class FetchParams:
    """Parameters for a single fetch page call."""

    query: dict[str, Any] = field(default_factory=dict)
    page: int = 1
    page_size: int = 50
    since: datetime | None = None
    until: datetime | None = None


@dataclass
class FetchResult:
    """Result from a single page fetch."""

    artifacts: list[dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    has_next: bool = False
    next_page: int | None = None
    raw_response_bytes: bytes = b""


@dataclass
class IngestRunResult:
    """Summary of a complete ingestion run."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    status: str = "completed"
    artifacts_fetched: int = 0
    artifacts_stored: int = 0
    artifacts_deduplicated: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BaseConnector(ABC):
    """Abstract base class for all federal data source connectors.

    Each connector implements rate-limited, idempotent fetching from a
    specific upstream API. The flow:
      1. run_incremental() or run_backfill() calls fetch_page() in a loop
      2. Each page returns raw artifacts with canonical URLs
      3. Content is hashed for deduplication
      4. Artifacts are yielded for storage and event emission
    """

    source_id: str
    rate_limit_rps: float
    base_url: str

    # Maximum pages per incremental run to prevent infinite loops
    MAX_PAGES_PER_RUN = 500

    def __init__(self, rate_limiter: RateLimiter | None = None) -> None:
        if rate_limiter is None:
            import logging
            logging.getLogger(__name__).warning(
                "connector=%s initialized without rate limiter — "
                "API calls will NOT be rate-limited. This is unsafe for production.",
                getattr(self, "source_id", "unknown"),
            )
        self._rate_limiter = rate_limiter
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=httpx.Timeout(
                    connect=DEFAULT_CONNECT_TIMEOUT,
                    read=DEFAULT_READ_TIMEOUT,
                    write=DEFAULT_READ_TIMEOUT,
                    pool=DEFAULT_READ_TIMEOUT,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _rate_limited_get(
        self, url: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        """Perform a GET request with rate limiting."""
        import logging

        _log = logging.getLogger(__name__)
        if self._rate_limiter:
            await self._rate_limiter.wait_for_token(self.source_id)
        _log.debug(
            "connector_get source=%s url=%s", self.source_id, url,
        )
        client = await self._get_client()
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response

    async def _rate_limited_post(
        self, url: str, json_body: dict[str, Any] | None = None
    ) -> httpx.Response:
        """Perform a POST request with rate limiting."""
        import logging

        _log = logging.getLogger(__name__)
        if self._rate_limiter:
            await self._rate_limiter.wait_for_token(self.source_id)
        _log.debug(
            "connector_post source=%s url=%s", self.source_id, url,
        )
        client = await self._get_client()
        response = await client.post(url, json=json_body)
        response.raise_for_status()
        return response

    @abstractmethod
    async def fetch_page(self, params: FetchParams) -> FetchResult:
        """Fetch a single page of results from the upstream API."""
        ...

    @abstractmethod
    def canonical_url(self, artifact: dict[str, Any]) -> str:
        """Return the canonical URL for deduplication of a single artifact."""
        ...

    @abstractmethod
    def doc_type(self) -> str:
        """Return the document type string for this connector's artifacts."""
        ...

    async def run_incremental(
        self, since: datetime, until: datetime | None = None
    ) -> IngestRunResult:
        """Run an incremental fetch for artifacts newer than `since`."""
        result = IngestRunResult(source_id=self.source_id, started_at=since)
        params = FetchParams(since=since, until=until)

        pages_fetched = 0
        try:
            while pages_fetched < self.MAX_PAGES_PER_RUN:
                pages_fetched += 1
                page_result = await self.fetch_page(params)
                for artifact_data in page_result.artifacts:
                    raw_bytes = self._serialize_artifact(artifact_data)
                    artifact_hash = content_hash(raw_bytes)
                    artifact_data["_content_hash"] = artifact_hash
                    artifact_data["_canonical_url"] = self.canonical_url(artifact_data)
                    artifact_data["_raw_bytes"] = raw_bytes
                    artifact_data["_doc_type"] = self.doc_type()
                    result.artifacts_fetched += 1

                if not page_result.has_next or page_result.next_page is None:
                    break
                params.page = page_result.next_page
        except Exception as exc:
            result.errors.append(str(exc))
            result.status = "partial"
        finally:
            result.completed_at = datetime.now()

        return result

    async def run_backfill(
        self, start: date, end: date
    ) -> IngestRunResult:
        """Run a full backfill for a date range."""
        from datetime import datetime as dt

        since = dt.combine(start, dt.min.time())
        until = dt.combine(end, dt.max.time())
        return await self.run_incremental(since=since, until=until)

    @staticmethod
    def _serialize_artifact(artifact: dict[str, Any]) -> bytes:
        """Deterministically serialize an artifact dict to bytes for hashing."""
        import json

        cleaned = {
            k: v
            for k, v in artifact.items()
            if not k.startswith("_") and v is not None
        }
        return json.dumps(cleaned, sort_keys=True, default=str).encode("utf-8")
