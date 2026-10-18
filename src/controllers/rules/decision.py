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


DECISION_SEVERITY = {"approved": 0, "two_factor_required": 1, "rejected": 2}
SCORE_PARTS_ABATED_BY_REDUCER = {
    LongRegisteredDevice.code: ("identity",),
    KnownDestination.code: ("relationship",),
    SameOwner.code: ("relationship", "amount"),
}


@dataclass
class AnalysisOutcome:
    decision: str
    rule_hits: list = field(default_factory=list)
    risk_score: Optional[int] = None
    destination_risk_score: Optional[int] = None
    two_factor_expires_at: Optional[datetime] = None


@dataclass
class ScoreParts:
    points: defaultdict = field(default_factory=lambda: defaultdict(int))
    reductions: defaultdict = field(default_factory=lambda: defaultdict(int))

    def capped_and_reduced(self, score_part: str, score_part_cap: int) -> int:
        return max(0, min(self.points[score_part], score_part_cap) + self.reductions[score_part])

    def reduced(self, score_part: str) -> int:
        return max(0, self.points[score_part] + self.reductions[score_part])


def fired_rule_hits(rules: list, context: TransactionContext) -> list:
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
        eliminatory_hits = fired_rule_hits(self.eliminatory_rules, context)

        if eliminatory_hits:
            return AnalysisOutcome(decision="rejected", rule_hits=eliminatory_hits)

        scoring_hits = fired_rule_hits(self.scoring_and_reducer_rules, context)
        regulatory_hits = fired_rule_hits(self.regulatory_rules, context)
        score_parts = self.score_parts_of(scoring_hits)
        risk_score = self.risk_score(score_parts, context.policy_version)
        decision = self.decision_for_risk_score(risk_score, context.policy_version)

        for regulatory_hit in regulatory_hits:
            forced_decision = self.rules_by_code[regulatory_hit.code].forced_decision.enumerator
            if DECISION_SEVERITY[forced_decision] > DECISION_SEVERITY[decision]:
                decision = forced_decision

        two_factor_expires_at = None
        if decision == "two_factor_required":
            two_factor_expires_at = context.transaction_date + timedelta(minutes=context.policy_version.two_factor_validity_minutes)

        return AnalysisOutcome(
            decision=decision,
            rule_hits=regulatory_hits + scoring_hits,
            risk_score=risk_score,
            destination_risk_score=self.destination_risk_score(score_parts),
            two_factor_expires_at=two_factor_expires_at,
        )

    def score_parts_of(self, scoring_hits: list) -> ScoreParts:
        score_parts = ScoreParts()

        for rule_hit in scoring_hits:
            rule = self.rules_by_code[rule_hit.code]
            if rule.kind == "reducer":
                for score_part in SCORE_PARTS_ABATED_BY_REDUCER[rule.code]:
                    score_parts.reductions[score_part] += rule_hit.points
            else:
                score_parts.points[rule.counterparty_signal or rule.family] += rule_hit.points

        return score_parts

    @staticmethod
    def risk_score(score_parts: ScoreParts, policy_version) -> int:
        identity_points = score_parts.capped_and_reduced("identity", policy_version.identity_family_cap)
        velocity_points = score_parts.capped_and_reduced("velocity", policy_version.velocity_family_cap)
        amount_points = score_parts.capped_and_reduced("amount", policy_version.amount_family_cap)
        relationship_points = score_parts.capped_and_reduced("relationship", policy_version.counterparty_relationship_cap)
        counterparty_points = min(relationship_points + score_parts.points["base"], policy_version.counterparty_family_cap)
        base_evidence_points = counterparty_points - relationship_points
        behavior_points = min(velocity_points + amount_points + relationship_points, policy_version.behavior_score_cap)
        return identity_points + behavior_points + base_evidence_points

    @staticmethod
    def decision_for_risk_score(risk_score: int, policy_version) -> str:
        if risk_score >= policy_version.rejection_score_threshold:
            return "rejected"

        if risk_score >= policy_version.two_factor_score_threshold:
            return "two_factor_required"

        return "approved"

    @staticmethod
    def destination_risk_score(score_parts: ScoreParts) -> int:
        return score_parts.reduced("relationship") + score_parts.points["base"]
