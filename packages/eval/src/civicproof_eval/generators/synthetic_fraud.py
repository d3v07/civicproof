from __future__ import annotations

import random
import string
import uuid
from dataclasses import dataclass, field
from typing import Any


def _random_uei() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=12))  # noqa: S311


def _random_cage() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=5))  # noqa: S311


def _random_company_name(suffix: str = "") -> str:
    prefixes = [
        "Apex", "Global", "Dynamic", "Strategic", "Premier", "Advanced",
        "Integrated", "National", "Federal", "United", "Allied", "Delta",
    ]
    middles = [
        "Solutions", "Systems", "Technologies", "Services", "Consulting",
        "Enterprises", "Holdings", "Group", "Associates", "Partners",
    ]
    return f"{random.choice(prefixes)} {random.choice(middles)} {suffix}".strip()  # noqa: S311


@dataclass
class SyntheticVendor:
    entity_id: str
    canonical_name: str
    uei: str
    cage_code: str
    aliases: list[str]
    is_shell: bool
    parent_entity_id: str | None
    state_of_incorporation: str
    award_ids: list[str] = field(default_factory=list)


@dataclass
class SyntheticAward:
    award_id: str
    vendor_entity_id: str
    amount_usd: float
    description: str
    period_of_performance_start: str
    period_of_performance_end: str
    awarding_agency: str
    flags: list[str] = field(default_factory=list)


@dataclass
class SyntheticFraudScenario:
    scenario_id: str
    scenario_type: str
    vendors: list[SyntheticVendor]
    awards: list[SyntheticAward]
    relationships: list[dict[str, Any]]
    expected_risk_signals: list[str]
    description: str


class SyntheticFraudGenerator:
    STATES = ["DE", "WY", "NV", "FL", "TX", "NY", "CA", "VA", "MD"]
    AGENCIES = [
        "Department of Defense",
        "Department of Veterans Affairs",
        "Department of Homeland Security",
        "General Services Administration",
        "Department of Energy",
    ]
    RISK_PATTERNS = [
        "shell_company_network",
        "bid_rigging",
        "cost_inflation",
        "phantom_subcontractor",
        "single_source_award_concentration",
        "related_party_transaction",
    ]

    def __init__(self, seed: int | None = None) -> None:
        if seed is not None:
            random.seed(seed)  # noqa: S311

    def generate_shell_company_network(self, depth: int = 3) -> SyntheticFraudScenario:
        scenario_id = str(uuid.uuid4())
        vendors: list[SyntheticVendor] = []
        awards: list[SyntheticAward] = []
        relationships: list[dict[str, Any]] = []

        root_vendor = SyntheticVendor(
            entity_id=str(uuid.uuid4()),
            canonical_name=_random_company_name("LLC"),
            uei=_random_uei(),
            cage_code=_random_cage(),
            aliases=[_random_company_name("Inc")],
            is_shell=False,
            parent_entity_id=None,
            state_of_incorporation=random.choice(self.STATES),  # noqa: S311
        )
        vendors.append(root_vendor)

        parent_id = root_vendor.entity_id
        for layer in range(depth):
            shell = SyntheticVendor(
                entity_id=str(uuid.uuid4()),
                canonical_name=_random_company_name(f"Holdings Layer{layer + 1}"),
                uei=_random_uei(),
                cage_code=_random_cage(),
                aliases=[],
                is_shell=True,
                parent_entity_id=parent_id,
                state_of_incorporation="DE",
            )
            vendors.append(shell)
            relationships.append(
                {
                    "source_entity_id": shell.entity_id,
                    "target_entity_id": parent_id,
                    "rel_type": "subsidiary_of",
                    "confidence": 0.9,
                }
            )
            parent_id = shell.entity_id

        leaf_vendor = vendors[-1]
        for i in range(random.randint(2, 5)):  # noqa: S311
            award = SyntheticAward(
                award_id=f"AWARD-SYN-{uuid.uuid4().hex[:8].upper()}",
                vendor_entity_id=leaf_vendor.entity_id,
                amount_usd=random.uniform(100_000, 10_000_000),  # noqa: S311
                description=f"Professional services contract {i + 1}",
                period_of_performance_start="2023-01-01",
                period_of_performance_end="2023-12-31",
                awarding_agency=random.choice(self.AGENCIES),  # noqa: S311
                flags=["shell_company_suspected", "multi_layer_ownership"],
            )
            awards.append(award)
            leaf_vendor.award_ids.append(award.award_id)

        return SyntheticFraudScenario(
            scenario_id=scenario_id,
            scenario_type="shell_company_network",
            vendors=vendors,
            awards=awards,
            relationships=relationships,
            expected_risk_signals=[
                "multi_layer_shell_structure",
                "single_state_incorporation_pattern",
                "award_concentration",
            ],
            description=f"Shell company network with {depth} layers and {len(awards)} awards",
        )

    def generate_bid_rigging_scenario(self, vendor_count: int = 4) -> SyntheticFraudScenario:
        scenario_id = str(uuid.uuid4())
        vendors: list[SyntheticVendor] = []
        awards: list[SyntheticAward] = []
        relationships: list[dict[str, Any]] = []

        controlling_individual_id = str(uuid.uuid4())
        for i in range(vendor_count):
            vendor = SyntheticVendor(
                entity_id=str(uuid.uuid4()),
                canonical_name=_random_company_name(f"Co{i + 1}"),
                uei=_random_uei(),
                cage_code=_random_cage(),
                aliases=[],
                is_shell=i > 0,
                parent_entity_id=None,
                state_of_incorporation=random.choice(["DE", "WY"]),  # noqa: S311
            )
            vendors.append(vendor)
            relationships.append(
                {
                    "source_entity_id": controlling_individual_id,
                    "target_entity_id": vendor.entity_id,
                    "rel_type": "owns",
                    "confidence": 0.85,
                }
            )

        winner = vendors[0]
        base_amount = random.uniform(500_000, 5_000_000)  # noqa: S311
        award = SyntheticAward(
            award_id=f"AWARD-SYN-{uuid.uuid4().hex[:8].upper()}",
            vendor_entity_id=winner.entity_id,
            amount_usd=base_amount,
            description="IT infrastructure services",
            period_of_performance_start="2023-03-01",
            period_of_performance_end="2024-02-28",
            awarding_agency=random.choice(self.AGENCIES),  # noqa: S311
            flags=["bid_rigging_suspected", "common_ownership"],
        )
        awards.append(award)
        winner.award_ids.append(award.award_id)

        return SyntheticFraudScenario(
            scenario_id=scenario_id,
            scenario_type="bid_rigging",
            vendors=vendors,
            awards=awards,
            relationships=relationships,
            expected_risk_signals=["common_ownership_competing_bidders", "award_concentration"],
            description=f"Bid rigging with {vendor_count} vendors sharing common ownership",
        )

    def generate_dataset(self, n_scenarios: int = 20) -> list[dict[str, Any]]:
        dataset: list[dict[str, Any]] = []
        generators = [
            self.generate_shell_company_network,
            self.generate_bid_rigging_scenario,
        ]

        for i in range(n_scenarios):
            gen = generators[i % len(generators)]
            scenario = gen()
            record: dict[str, Any] = {
                "case_id": scenario.scenario_id,
                "scenario_type": scenario.scenario_type,
                "vendors": [
                    {
                        "entity_id": v.entity_id,
                        "canonical_name": v.canonical_name,
                        "uei": v.uei,
                        "cage_code": v.cage_code,
                        "is_shell": v.is_shell,
                        "parent_entity_id": v.parent_entity_id,
                    }
                    for v in scenario.vendors
                ],
                "awards": [
                    {
                        "award_id": a.award_id,
                        "vendor_entity_id": a.vendor_entity_id,
                        "amount_usd": a.amount_usd,
                        "awarding_agency": a.awarding_agency,
                        "flags": a.flags,
                    }
                    for a in scenario.awards
                ],
                "relationships": scenario.relationships,
                "expected_risk_signals": scenario.expected_risk_signals,
                "description": scenario.description,
            }
            dataset.append(record)

        return dataset
