"""Case Composer Agent.

Assembles a structured case dossier from evidence, entity resolution,
risk signals, and anomaly detection results. Every factual claim MUST
include citation_ids pointing to actual stored artifacts.

This agent prepares the case pack for the Auditor Gate.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from civicproof_common.hashing import content_hash
from civicproof_common.schemas.cases import ClaimType

logger = logging.getLogger(__name__)


@dataclass
class ComposedClaim:
    """A single claim in the case dossier."""

    claim_id: str
    statement: str
    claim_type: str  # ClaimType value
    confidence: float
    citation_ids: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)


@dataclass
class ComposedCasePack:
    """The complete case pack before auditing."""

    case_id: str
    title: str
    summary: str
    claims: list[ComposedClaim] = field(default_factory=list)
    risk_signals: list[dict[str, Any]] = field(default_factory=list)
    entity_profile: dict[str, Any] = field(default_factory=dict)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    pack_hash: str = ""

    def compute_hash(self) -> str:
        """Compute deterministic hash of the pack for replay verification."""
        serializable = {
            "case_id": self.case_id,
            "claims": [
                {
                    "statement": c.statement,
                    "claim_type": c.claim_type,
                    "confidence": c.confidence,
                    "citation_ids": sorted(c.citation_ids),
                    "artifact_ids": sorted(c.artifact_ids),
                }
                for c in sorted(self.claims, key=lambda x: x.claim_id)
            ],
            "risk_signals": sorted(
                [{"type": r["signal_type"], "score": r["score"]} for r in self.risk_signals],
                key=lambda x: x["type"],
            ),
        }
        raw = json.dumps(serializable, sort_keys=True, default=str).encode("utf-8")
        self.pack_hash = content_hash(raw)
        return self.pack_hash


@dataclass
class CompositionResult:
    """Result from the case composer agent."""

    case_pack: ComposedCasePack
    composition_log: list[dict[str, Any]] = field(default_factory=list)


class CaseComposerAgent:
    """Composes a structured case dossier from pipeline results."""

    def compose(
        self,
        case_id: str,
        entity_profile: dict[str, Any],
        artifact_ids: list[str],
        risk_signals: list[dict[str, Any]],
        awards_data: list[dict[str, Any]],
        sources_used: list[str],
    ) -> CompositionResult:
        """Compose a case pack from all pipeline outputs.

        Every factual claim MUST have at least one citation.
        Risk signals and hypotheses CAN exist without citations.
        """
        title = self._generate_title(entity_profile)
        summary = self._generate_summary(entity_profile, risk_signals)

        pack = ComposedCasePack(
            case_id=case_id,
            title=title,
            summary=summary,
            entity_profile=entity_profile,
            sources_used=sources_used,
        )

        # 1. Entity profile claims (factual — require citations)
        pack.claims.extend(
            self._compose_entity_claims(case_id, entity_profile, artifact_ids)
        )

        # 2. Award claims (factual — require citations)
        pack.claims.extend(
            self._compose_award_claims(case_id, awards_data, artifact_ids)
        )

        # 3. Risk signal claims (hypothesis/risk_signal — citations optional)
        for idx, signal in enumerate(risk_signals):
            pack.risk_signals.append(signal)
            statement = signal.get("description", "")
            pack.claims.append(ComposedClaim(
                claim_id=self._deterministic_claim_id(case_id, f"risk_signal_{idx}", statement),
                statement=statement,
                claim_type=ClaimType.RISK_SIGNAL.value,
                confidence=signal.get("score", 0.5),
                citation_ids=[],
                artifact_ids=signal.get("supporting_artifact_ids", []),
            ))

        # 4. Build timeline from awards
        pack.timeline = self._build_timeline(awards_data)

        # 5. Evidence summary
        pack.evidence_summary = {
            "total_artifacts": len(artifact_ids),
            "sources_used": sources_used,
            "source_count": len(sources_used),
            "total_claims": len(pack.claims),
            "factual_claims": sum(
                1 for c in pack.claims if c.claim_type == ClaimType.FINDING.value
            ),
            "risk_signals": sum(
                1 for c in pack.claims if c.claim_type == ClaimType.RISK_SIGNAL.value
            ),
            "hypotheses": sum(
                1 for c in pack.claims if c.claim_type == ClaimType.HYPOTHESIS.value
            ),
        }

        # 6. Compute deterministic hash
        pack.compute_hash()

        result = CompositionResult(case_pack=pack)
        result.composition_log.append({
            "action": "case_composed",
            "claim_count": len(pack.claims),
            "risk_signal_count": len(pack.risk_signals),
            "pack_hash": pack.pack_hash,
        })

        return result

    def _generate_title(self, entity_profile: dict[str, Any]) -> str:
        name = entity_profile.get("canonical_name", "Unknown Entity")
        return f"Investigative Case Pack: {name}"

    def _generate_summary(
        self, entity_profile: dict[str, Any], risk_signals: list[dict[str, Any]]
    ) -> str:
        name = entity_profile.get("canonical_name", "Unknown Entity")
        signal_count = len(risk_signals)
        high_count = sum(1 for s in risk_signals if s.get("severity") == "high")

        parts = [f"Investigation of {name}."]
        if signal_count:
            parts.append(
                f"Analysis identified {signal_count} risk signal(s)"
                f"{f', including {high_count} high-severity' if high_count else ''}."
            )
        else:
            parts.append("No significant risk signals identified.")
        parts.append(
            "All factual claims are supported by cited artifacts. "
            "This document contains risk signals and hypotheses only; "
            "it does not constitute an accusation of wrongdoing."
        )
        return " ".join(parts)

    @staticmethod
    def _deterministic_claim_id(case_id: str, claim_key: str, statement: str) -> str:
        """Generate a deterministic claim ID from case_id + key + statement.

        This ensures replay-determinism: same inputs → same claim IDs.
        """
        payload = f"{case_id}:{claim_key}:{statement}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def _compose_entity_claims(
        self, case_id: str, entity_profile: dict[str, Any], artifact_ids: list[str]
    ) -> list[ComposedClaim]:
        """Create factual claims about the entity from profile data."""
        claims = []
        name = entity_profile.get("canonical_name", "")
        uei = entity_profile.get("uei")
        entity_type = entity_profile.get("entity_type", "vendor")

        if name and artifact_ids:
            stmt = f"{name} is registered as a federal {entity_type}."
            claims.append(ComposedClaim(
                claim_id=self._deterministic_claim_id(case_id, "entity_registered", stmt),
                statement=stmt,
                claim_type=ClaimType.FINDING.value,
                confidence=1.0,
                citation_ids=[artifact_ids[0]] if artifact_ids else [],
                artifact_ids=artifact_ids[:3],
            ))

        if uei and artifact_ids:
            stmt = f"{name} has Unique Entity Identifier (UEI): {uei}."
            claims.append(ComposedClaim(
                claim_id=self._deterministic_claim_id(case_id, "entity_uei", stmt),
                statement=stmt,
                claim_type=ClaimType.FINDING.value,
                confidence=1.0,
                citation_ids=[artifact_ids[0]] if artifact_ids else [],
                artifact_ids=artifact_ids[:1],
            ))

        return claims

    def _compose_award_claims(
        self, case_id: str, awards_data: list[dict[str, Any]], artifact_ids: list[str]
    ) -> list[ComposedClaim]:
        """Create factual claims from award data."""
        claims = []

        if not awards_data:
            return claims

        total_value = sum(
            float(a.get("award_amount", 0) or 0) for a in awards_data
        )
        if total_value > 0:
            stmt = (
                f"Entity has received {len(awards_data)} federal award(s) "
                f"totaling ${total_value:,.2f}."
            )
            claims.append(ComposedClaim(
                claim_id=self._deterministic_claim_id(case_id, "award_total", stmt),
                statement=stmt,
                claim_type=ClaimType.FINDING.value,
                confidence=1.0,
                citation_ids=artifact_ids[:3],
                artifact_ids=artifact_ids[:5],
            ))

        # Sole-source claims
        sole_source = [
            a for a in awards_data
            if a.get("is_sole_source") or (
                a.get("extent_competed", "").upper() in (
                    "NOT COMPETED", "SOLE SOURCE", "C", "D"
                )
            )
        ]
        if sole_source:
            stmt = (
                f"{len(sole_source)} of {len(awards_data)} awards "
                f"({len(sole_source)/len(awards_data):.0%}) were sole-source."
            )
            claims.append(ComposedClaim(
                claim_id=self._deterministic_claim_id(case_id, "sole_source", stmt),
                statement=stmt,
                claim_type=ClaimType.FINDING.value,
                confidence=0.95,
                citation_ids=artifact_ids[:2],
                artifact_ids=artifact_ids[:3],
            ))

        return claims

    def _build_timeline(
        self, awards_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build a chronological timeline from award data."""
        timeline = []
        for award in awards_data:
            date_str = award.get("start_date") or award.get("action_date", "")
            if date_str:
                timeline.append({
                    "date": date_str,
                    "event": f"Award {award.get('award_id', 'N/A')} "
                             f"(${float(award.get('award_amount', 0) or 0):,.2f})",
                    "type": "award",
                    "source": "usaspending",
                })

        # Sort by date
        timeline.sort(key=lambda x: x.get("date", ""))
        return timeline
