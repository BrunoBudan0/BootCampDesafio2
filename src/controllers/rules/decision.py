from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from controllers.rules.catalog import (
    AmountAboveBaseline,
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
DESTINATION_RELATIONSHIP_REDUCERS = (SameOwner.code, KnownDestination.code)


@dataclass
class AnalysisOutcome:
    decision: str
    rule_hits: list = field(default_factory=list)
    risk_score: Optional[int] = None
    destination_risk: Optional[int] = None
    two_factor_expires_at: Optional[datetime] = None


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
        risk_score = self.risk_score(scoring_hits, context)
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
            destination_risk=self.destination_risk(scoring_hits),
            two_factor_expires_at=two_factor_expires_at,
        )

    def risk_score(self, scoring_hits: list, context: TransactionContext) -> int:
        family_points = {}
        reducer_points = 0

        for rule_hit in scoring_hits:
            rule = self.rules_by_code[rule_hit.code]
            if rule.kind == "reducer":
                reducer_points += rule_hit.points
            else:
                family_points[rule.family] = family_points.get(rule.family, 0) + rule_hit.points

        capped_points = sum(
            min(points, getattr(context.policy, f"{family}_family_cap")) for family, points in family_points.items()
        )
        return max(0, capped_points + reducer_points)

    @staticmethod
    def score_band(risk_score: int, context: TransactionContext) -> str:
        if risk_score >= context.policy.rejection_score_threshold:
            return "rejected"

        if risk_score >= context.policy.two_factor_score_threshold:
            return "two_factor_required"

        return "approved"

    def destination_risk(self, scoring_hits: list) -> int:
        relationship_points = 0
        base_points = 0

        for rule_hit in scoring_hits:
            rule = self.rules_by_code[rule_hit.code]
            if rule.counterparty_signal == "relationship" or rule.code in DESTINATION_RELATIONSHIP_REDUCERS:
                relationship_points += rule_hit.points
            elif rule.counterparty_signal == "base":
                base_points += rule_hit.points

        return max(0, relationship_points) + base_points
