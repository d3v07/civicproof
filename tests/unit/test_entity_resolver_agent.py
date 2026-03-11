"""Unit tests for EntityResolverAgent with mocked DB."""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from src.agents.entity_resolver import EntityResolverAgent, ResolvedEntity  # noqa: E402


def _mock_entity_row(**overrides):
    defaults = dict(
        entity_id="ent-001",
        canonical_name="ACME CORP",
        entity_type="vendor",
        uei="ABC123DEF456",
        cage_code="1A2B3",
        aliases=["Acme Corporation"],
        metadata_={"source": "test"},
    )
    defaults.update(overrides)
    row = MagicMock()
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


class TestResolveDeterministic:
    @pytest.mark.asyncio
    async def test_finds_by_uei(self):
        mock_db = AsyncMock()
        row = _mock_entity_row()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        agent = EntityResolverAgent(mock_db)
        result = await agent._resolve_deterministic({"uei": "ABC123DEF456"})

        assert result is not None
        assert result.entity_id == "ent-001"
        assert result.confidence == 1.0
        assert result.resolution_method == "deterministic"

    @pytest.mark.asyncio
    async def test_finds_by_cage_code(self):
        mock_db = AsyncMock()
        row = _mock_entity_row()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        agent = EntityResolverAgent(mock_db)
        result = await agent._resolve_deterministic({"cage_code": "1A2B3"})

        assert result is not None
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_returns_none_no_identifiers(self):
        mock_db = AsyncMock()
        agent = EntityResolverAgent(mock_db)
        result = await agent._resolve_deterministic({"vendor_name": "Acme"})
        assert result is None
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_not_found(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        agent = EntityResolverAgent(mock_db)
        result = await agent._resolve_deterministic({"uei": "NONEXISTENT12"})
        assert result is None


class TestResolveFuzzy:
    @pytest.mark.asyncio
    async def test_exact_canonical_match(self):
        mock_db = AsyncMock()
        row = _mock_entity_row()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        agent = EntityResolverAgent(mock_db)
        result = await agent._resolve_fuzzy("Acme Corp")

        assert result is not None
        assert result.confidence == 0.95
        assert result.resolution_method == "fuzzy"

    @pytest.mark.asyncio
    async def test_partial_match(self):
        mock_db = AsyncMock()

        # First query (exact) returns None
        mock_exact_result = MagicMock()
        mock_exact_result.scalar_one_or_none.return_value = None

        # Second query (LIKE) returns a match
        row = _mock_entity_row(canonical_name="ACME CORP INTERNATIONAL")
        mock_like_result = MagicMock()
        mock_like_result.scalars.return_value = iter([row])

        mock_db.execute = AsyncMock(side_effect=[mock_exact_result, mock_like_result])

        agent = EntityResolverAgent(mock_db)
        result = await agent._resolve_fuzzy("Acme Corp")

        assert result is not None
        assert result.confidence == 0.75

    @pytest.mark.asyncio
    async def test_empty_name_returns_none(self):
        mock_db = AsyncMock()
        agent = EntityResolverAgent(mock_db)
        result = await agent._resolve_fuzzy("")
        assert result is None


class TestResolveFullFlow:
    @pytest.mark.asyncio
    async def test_deterministic_match_first(self):
        mock_db = AsyncMock()
        row = _mock_entity_row()

        # deterministic query finds entity
        mock_det_result = MagicMock()
        mock_det_result.scalar_one_or_none.return_value = row

        # _find_related returns empty
        mock_rel_result = MagicMock()
        mock_rel_result.scalars.return_value = iter([])

        mock_db.execute = AsyncMock(side_effect=[mock_det_result, mock_rel_result])

        agent = EntityResolverAgent(mock_db)
        result = await agent.resolve({"uei": "ABC123DEF456", "vendor_name": "Acme"})

        assert result.primary_entity is not None
        assert result.primary_entity.confidence == 1.0
        assert result.resolution_log[0]["tier"] == "deterministic"

    @pytest.mark.asyncio
    async def test_falls_to_fuzzy_when_no_identifiers(self):
        mock_db = AsyncMock()
        row = _mock_entity_row()

        # fuzzy exact match
        mock_fuzzy_result = MagicMock()
        mock_fuzzy_result.scalar_one_or_none.return_value = row

        # _find_related returns empty
        mock_rel_result = MagicMock()
        mock_rel_result.scalars.return_value = iter([])

        mock_db.execute = AsyncMock(side_effect=[mock_fuzzy_result, mock_rel_result])

        agent = EntityResolverAgent(mock_db)
        result = await agent.resolve({"vendor_name": "Acme Corp"})

        assert result.primary_entity is not None
        assert result.resolution_log[0]["tier"] == "fuzzy"

    @pytest.mark.asyncio
    async def test_creates_new_entity_when_no_match(self):
        mock_db = AsyncMock()

        # fuzzy exact → None
        mock_r1 = MagicMock()
        mock_r1.scalar_one_or_none.return_value = None
        # fuzzy LIKE → empty
        mock_r2 = MagicMock()
        mock_r2.scalars.return_value = iter([])
        # _find_related → empty
        mock_r3 = MagicMock()
        mock_r3.scalars.return_value = iter([])

        mock_db.execute = AsyncMock(side_effect=[mock_r1, mock_r2, mock_r3])
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        agent = EntityResolverAgent(mock_db)
        result = await agent.resolve({"vendor_name": "Brand New Corp"})

        assert result.primary_entity is not None
        assert result.primary_entity.resolution_method == "new_entity"
        assert result.primary_entity.confidence == 0.5
        mock_db.add.assert_called_once()


class TestResolvedEntity:
    def test_dataclass_defaults(self):
        e = ResolvedEntity(
            entity_id="e1", canonical_name="TEST",
            entity_type="vendor", confidence=0.9,
            resolution_method="fuzzy",
        )
        assert e.uei is None
        assert e.cage_code is None
        assert e.aliases == []
        assert e.metadata == {}
