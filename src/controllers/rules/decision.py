from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from controllers.rules.catalog import (
    AmountAboveBaseline,
    AmountFarAboveBaseline,
    BurstOfPix,
    ChannelUnfamiliar,
    DestinationAccountOpenedRecently,
    DestinationAccountOpenedVeryRecently,
    DestinationDocumentInManyAccounts,
    DestinationReceivingFromManySources,
    DestinationRejectedForOtherSources,
    DeviceUsedByManySources,
    ImpossibleTravel,
    ImpossibleTravelOnUnregisteredDevice,
    IpUnfamiliar,
    KnownDestination,
    LocationUnfamiliar,
    LongRegisteredDevice,
    MonthlyVolumeAboveTypical,
    NewAccountAboveCap,
    NewAccountToNewDestinationFarAboveCap,
    NewDestinationAboveUsualCeiling,
    NightlyLimitExceeded,
    SameOwner,
    TwoFactorDeniedRecently,
    UnregisteredDeviceLimitExceeded,
)
from controllers.rules.transaction_context import TransactionContext


SEVERITY = {"approved": 0, "two_factor_required": 1, "rejected": 2}
REDUCED_SCORE_PARTS = {
    LongRegisteredDevice.code: ("identity",),
    KnownDestination.code: ("relationship",),
    SameOwner.code: ("relationship", "amount"),
}


@dataclass
class AnalysisOutcome:
    decision: str
    rule_hits: list = field(default_factory=list)
    risk_score: Optional[int] = None
    destination_risk: Optional[int] = None
    two_factor_expires_at: Optional[datetime] = None


@dataclass
class ScoreParts:
    points: defaultdict = field(default_factory=lambda: defaultdict(int))
    reductions: defaultdict = field(default_factory=lambda: defaultdict(int))

    def capped_and_reduced(self, part: str, cap: int) -> int:
        return max(0, min(self.points[part], cap) + self.reductions[part])

    def reduced(self, part: str) -> int:
        return max(0, self.points[part] + self.reductions[part])


def evaluated_hits(rules: list, context: TransactionContext) -> list:
    return [rule_hit for rule_hit in (rule.evaluate(context) for rule in rules) if rule_hit is not None]


class AnalysisDecision:
    def __init__(self, rules_by_code: dict) -> None:
        self.rules_by_code = rules_by_code
        self.eliminatory_rules = [
            DeviceUsedByManySources(),
            ImpossibleTravelOnUnregisteredDevice(),
            NewAccountToNewDestinationFarAboveCap(),
        ]
        self.regulatory_rules = [NightlyLimitExceeded(), UnregisteredDeviceLimitExceeded()]
        self.scoring_and_reducer_rules = [
            ImpossibleTravel(),
            IpUnfamiliar(),
            LocationUnfamiliar(),
            ChannelUnfamiliar(),
            TwoFactorDeniedRecently(),
            NewAccountAboveCap(),
            BurstOfPix(),
            AmountAboveBaseline(),
            AmountFarAboveBaseline(),
            MonthlyVolumeAboveTypical(),
            DestinationAccountOpenedVeryRecently(),
            DestinationAccountOpenedRecently(),
            NewDestinationAboveUsualCeiling(),
            DestinationReceivingFromManySources(),
            DestinationRejectedForOtherSources(rules_by_code[DestinationRejectedForOtherSources.code].id),
            DestinationDocumentInManyAccounts(),
            SameOwner(),
            KnownDestination(),
            LongRegisteredDevice(),
        ]

    def decide(self, context: TransactionContext) -> AnalysisOutcome:
        eliminatory_hits = evaluated_hits(self.eliminatory_rules, context)

        if eliminatory_hits:
            return AnalysisOutcome(decision="rejected", rule_hits=eliminatory_hits)

        scoring_hits = evaluated_hits(self.scoring_and_reducer_rules, context)
        regulatory_hits = evaluated_hits(self.regulatory_rules, context)
        score_parts = self.score_parts(scoring_hits)
        risk_score = self.risk_score(score_parts, context.policy)
        decision = self.score_band(risk_score, context)

        for regulatory_hit in regulatory_hits:
            forced_decision = self.rules_by_code[regulatory_hit.code].forced_decision.enumerator
            if SEVERITY[forced_decision] > SEVERITY[decision]:
                decision = forced_decision

        two_factor_expires_at = None
        if decision == "two_factor_required":
            two_factor_expires_at = context.moment + timedelta(minutes=context.policy.two_factor_validity_minutes)

        return AnalysisOutcome(
            decision=decision,
            rule_hits=regulatory_hits + scoring_hits,
            risk_score=risk_score,
            destination_risk=self.destination_risk(score_parts),
            two_factor_expires_at=two_factor_expires_at,
        )

    def score_parts(self, scoring_hits: list) -> ScoreParts:
        parts = ScoreParts()

        for rule_hit in scoring_hits:
            rule = self.rules_by_code[rule_hit.code]
            if rule.kind == "reducer":
                for part in REDUCED_SCORE_PARTS[rule.code]:
                    parts.reductions[part] += rule_hit.points
            else:
                parts.points[rule.counterparty_signal or rule.family] += rule_hit.points

        return parts

    @staticmethod
    def risk_score(parts: ScoreParts, policy) -> int:
        identity = parts.capped_and_reduced("identity", policy.identity_family_cap)
        velocity = parts.capped_and_reduced("velocity", policy.velocity_family_cap)
        amount = parts.capped_and_reduced("amount", policy.amount_family_cap)
        relationship = parts.capped_and_reduced("relationship", policy.counterparty_relationship_cap)
        counterparty = min(relationship + parts.points["base"], policy.counterparty_family_cap)
        base_evidence = counterparty - relationship
        behavior = min(velocity + amount + relationship, policy.behavior_score_cap)
        return identity + behavior + base_evidence

    @staticmethod
    def score_band(risk_score: int, context: TransactionContext) -> str:
        if risk_score >= context.policy.rejection_score_threshold:
            return "rejected"

        if risk_score >= context.policy.two_factor_score_threshold:
            return "two_factor_required"

        return "approved"

    @staticmethod
    def destination_risk(parts: ScoreParts) -> int:
        return parts.reduced("relationship") + parts.points["base"]
