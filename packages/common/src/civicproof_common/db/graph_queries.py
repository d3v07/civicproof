"""Evidence graph queries using Postgres relational tables.

Provides graph traversal capabilities over the entity-relationship model:
- neighborhood(): BFS neighbors up to N hops
- shortest_path(): Dijkstra with confidence weights
- shared_connections(): common neighbors between entities
- subgraph(): induced subgraph from entity set
- motif_search(): detect ring patterns (shared addresses, officer overlap)
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from civicproof_common.db.models import EntityModel, RelationshipModel

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the evidence graph."""

    entity_id: str
    entity_type: str
    canonical_name: str
    uei: str | None = None
    cage_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """An edge in the evidence graph."""

    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    rel_type: str
    confidence: float = 0.5
    provenance_artifact_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphNeighborhood:
    """Result of a neighborhood query."""

    center_entity_id: str
    depth: int
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    @property
    def entity_ids(self) -> set[str]:
        return {n.entity_id for n in self.nodes}


@dataclass
class ShortestPath:
    """Result of a shortest path query."""

    source_id: str
    target_id: str
    path: list[str] = field(default_factory=list)  # entity_id sequence
    total_weight: float = float("inf")
    edges: list[GraphEdge] = field(default_factory=list)
    found: bool = False


class EvidenceGraph:
    """Graph traversal queries over the entity-relationship model.

    All queries are implemented as pure SQL over the existing
    entity + relationship tables — no dedicated graph DB needed.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def neighborhood(
        self, entity_id: str, depth: int = 2, max_nodes: int = 100
    ) -> GraphNeighborhood:
        """BFS traversal to find neighbors within `depth` hops."""
        result = GraphNeighborhood(center_entity_id=entity_id, depth=depth)
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])

        while queue and len(visited) < max_nodes:
            current_id, current_depth = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)

            # Fetch entity
            entity = await self._fetch_entity(current_id)
            if entity:
                result.nodes.append(entity)

            if current_depth >= depth:
                continue

            # Fetch edges
            edges = await self._fetch_edges(current_id)
            for edge in edges:
                result.edges.append(edge)
                neighbor_id = (
                    edge.target_entity_id
                    if edge.source_entity_id == current_id
                    else edge.source_entity_id
                )
                if neighbor_id not in visited:
                    queue.append((neighbor_id, current_depth + 1))

        return result

    async def shortest_path(
        self, source_id: str, target_id: str, max_depth: int = 5
    ) -> ShortestPath:
        """Dijkstra shortest path with confidence-based weights.

        Weight = 1.0 - confidence (higher confidence = lower weight = preferred).
        """
        import heapq

        result = ShortestPath(source_id=source_id, target_id=target_id)

        # dist[entity_id] = (total_weight, path, edges)
        dist: dict[str, tuple[float, list[str], list[GraphEdge]]] = {
            source_id: (0.0, [source_id], [])
        }
        pq: list[tuple[float, str]] = [(0.0, source_id)]
        visited: set[str] = set()

        while pq:
            current_weight, current_id = heapq.heappop(pq)
            if current_id in visited:
                continue
            visited.add(current_id)

            if current_id == target_id:
                result.path = dist[current_id][1]
                result.total_weight = dist[current_id][0]
                result.edges = dist[current_id][2]
                result.found = True
                return result

            if len(dist[current_id][1]) > max_depth:
                continue

            edges = await self._fetch_edges(current_id)
            for edge in edges:
                neighbor_id = (
                    edge.target_entity_id
                    if edge.source_entity_id == current_id
                    else edge.source_entity_id
                )
                if neighbor_id in visited:
                    continue

                edge_weight = 1.0 - edge.confidence
                new_weight = current_weight + edge_weight
                if neighbor_id not in dist or new_weight < dist[neighbor_id][0]:
                    new_path = dist[current_id][1] + [neighbor_id]
                    new_edges = dist[current_id][2] + [edge]
                    dist[neighbor_id] = (new_weight, new_path, new_edges)
                    heapq.heappush(pq, (new_weight, neighbor_id))

        return result

    async def shared_connections(
        self, entity_a_id: str, entity_b_id: str
    ) -> list[GraphNode]:
        """Find entities that are connected to both entity_a and entity_b."""
        neighbors_a = await self._get_neighbor_ids(entity_a_id)
        neighbors_b = await self._get_neighbor_ids(entity_b_id)
        shared_ids = neighbors_a & neighbors_b

        shared_nodes = []
        for eid in shared_ids:
            node = await self._fetch_entity(eid)
            if node:
                shared_nodes.append(node)
        return shared_nodes

    async def subgraph(self, entity_ids: list[str]) -> GraphNeighborhood:
        """Return the induced subgraph containing only the specified entities."""
        result = GraphNeighborhood(
            center_entity_id=entity_ids[0] if entity_ids else "",
            depth=0,
        )
        id_set = set(entity_ids)

        for eid in entity_ids:
            node = await self._fetch_entity(eid)
            if node:
                result.nodes.append(node)

        # Fetch all edges between these entities
        if entity_ids:
            stmt = select(RelationshipModel).where(
                RelationshipModel.source_entity_id.in_(entity_ids),
                RelationshipModel.target_entity_id.in_(entity_ids),
            )
            rows = await self._db.execute(stmt)
            for row in rows.scalars():
                result.edges.append(self._row_to_edge(row))

        return result

    async def motif_search(
        self, pattern: str = "shared_address"
    ) -> list[dict[str, Any]]:
        """Search for known graph motifs indicating potential fraud patterns.

        Patterns:
        - shared_address: 3+ entities sharing an address
        - officer_overlap: same officer across multiple vendor entities
        - hub_and_spoke: one entity connected to many others with same rel_type
        """
        if pattern == "shared_address":
            return await self._find_shared_address_rings()
        elif pattern == "officer_overlap":
            return await self._find_officer_overlaps()
        elif pattern == "hub_and_spoke":
            return await self._find_hub_and_spoke()
        else:
            logger.warning("unknown motif pattern: %s", pattern)
            return []

    # ── Private helpers ───────────────────────────────────────────

    async def _fetch_entity(self, entity_id: str) -> GraphNode | None:
        stmt = select(EntityModel).where(EntityModel.entity_id == entity_id)
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return GraphNode(
            entity_id=row.entity_id,
            entity_type=row.entity_type,
            canonical_name=row.canonical_name,
            uei=row.uei,
            cage_code=row.cage_code,
            metadata=row.metadata_ or {},
        )

    async def _fetch_edges(self, entity_id: str) -> list[GraphEdge]:
        stmt = select(RelationshipModel).where(
            or_(
                RelationshipModel.source_entity_id == entity_id,
                RelationshipModel.target_entity_id == entity_id,
            )
        )
        result = await self._db.execute(stmt)
        return [self._row_to_edge(row) for row in result.scalars()]

    async def _get_neighbor_ids(self, entity_id: str) -> set[str]:
        edges = await self._fetch_edges(entity_id)
        neighbors = set()
        for edge in edges:
            neighbors.add(edge.source_entity_id)
            neighbors.add(edge.target_entity_id)
        neighbors.discard(entity_id)
        return neighbors

    @staticmethod
    def _row_to_edge(row: RelationshipModel) -> GraphEdge:
        return GraphEdge(
            relationship_id=row.relationship_id,
            source_entity_id=row.source_entity_id,
            target_entity_id=row.target_entity_id,
            rel_type=row.rel_type,
            confidence=row.confidence or 0.5,
            provenance_artifact_id=row.provenance_artifact_id,
            metadata=row.metadata_ or {},
        )

    async def _find_shared_address_rings(self) -> list[dict[str, Any]]:
        """Find 3+ entities sharing the same address metadata."""
        # Query entities grouped by address in metadata
        stmt = text("""
            SELECT
                metadata_->>'address' as address,
                array_agg(entity_id) as entity_ids,
                count(*) as entity_count
            FROM entity
            WHERE metadata_->>'address' IS NOT NULL
              AND metadata_->>'address' != ''
            GROUP BY metadata_->>'address'
            HAVING count(*) >= 3
            ORDER BY count(*) DESC
        """)
        result = await self._db.execute(stmt)
        rings = []
        for row in result:
            rings.append({
                "pattern": "shared_address_ring",
                "address": row.address,
                "entity_ids": list(row.entity_ids),
                "entity_count": row.entity_count,
                "severity": "high" if row.entity_count >= 5 else "medium",
            })
        return rings

    async def _find_officer_overlaps(self) -> list[dict[str, Any]]:
        """Find individuals connected to multiple vendor entities."""
        stmt = text("""
            SELECT
                r.source_entity_id as individual_id,
                e_ind.canonical_name as individual_name,
                array_agg(DISTINCT r.target_entity_id) as vendor_ids,
                count(DISTINCT r.target_entity_id) as vendor_count
            FROM relationship r
            JOIN entity e_ind ON r.source_entity_id = e_ind.entity_id
            JOIN entity e_vendor ON r.target_entity_id = e_vendor.entity_id
            WHERE r.rel_type IN ('employs', 'affiliated_with', 'owns')
              AND e_ind.entity_type = 'individual'
              AND e_vendor.entity_type = 'vendor'
            GROUP BY r.source_entity_id, e_ind.canonical_name
            HAVING count(DISTINCT r.target_entity_id) >= 2
            ORDER BY count(DISTINCT r.target_entity_id) DESC
        """)
        result = await self._db.execute(stmt)
        overlaps = []
        for row in result:
            overlaps.append({
                "pattern": "officer_overlap",
                "individual_id": row.individual_id,
                "individual_name": row.individual_name,
                "vendor_ids": list(row.vendor_ids),
                "vendor_count": row.vendor_count,
                "severity": "high" if row.vendor_count >= 3 else "medium",
            })
        return overlaps

    async def _find_hub_and_spoke(self) -> list[dict[str, Any]]:
        """Find hub entities connected to many others via the same rel type."""
        stmt = text("""
            SELECT
                source_entity_id,
                e.canonical_name,
                rel_type,
                count(DISTINCT target_entity_id) as connection_count
            FROM relationship r
            JOIN entity e ON r.source_entity_id = e.entity_id
            GROUP BY source_entity_id, e.canonical_name, rel_type
            HAVING count(DISTINCT target_entity_id) >= 5
            ORDER BY count(DISTINCT target_entity_id) DESC
        """)
        result = await self._db.execute(stmt)
        hubs = []
        for row in result:
            hubs.append({
                "pattern": "hub_and_spoke",
                "hub_entity_id": row.source_entity_id,
                "hub_name": row.canonical_name,
                "rel_type": row.rel_type,
                "connection_count": row.connection_count,
                "severity": "medium",
            })
        return hubs
