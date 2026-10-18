from dataclasses import dataclass

from controllers.rules.catalog import RuleHit
from controllers.rules.credibility import points_weighted_by_history
from controllers.rules.decision import DECISION_SEVERITY, AnalysisDecision


ANCHOR_CASE_ACCEPTED_HISTORY_COUNT = 20


@dataclass(frozen=True)
class AnchorCase:
    name: str
    description: str
    rule_names: tuple
    minimum_decision: str
    requires_alert: bool


@dataclass(frozen=True)
class AnchorOutcome:
    decision: str
    risk_score: int
    raises_alert: bool

    def reaches_the_minimum_of(self, anchor_case: AnchorCase) -> bool:
        reaches_the_decision = DECISION_SEVERITY[self.decision] >= DECISION_SEVERITY[anchor_case.minimum_decision]
        return reaches_the_decision and (self.raises_alert or not anchor_case.requires_alert)


ANCHOR_CASES = (
    AnchorCase(
        name="account_takeover_with_high_amount",
        description="Invasão de conta com valor alto",
        rule_names=("ip_unfamiliar", "location_unfamiliar", "channel_unfamiliar", "amount_far_above_baseline", "new_destination_above_usual_ceiling"),
        minimum_decision="rejected",
        requires_alert=False,
    ),
    AnchorCase(
        name="mule_flagged_by_the_base",
        description="Laranja marcado pela base",
        rule_names=(
            "new_destination_above_usual_ceiling",
            "destination_receiving_from_many_sources",
            "destination_document_in_many_accounts",
            "destination_rejected_for_other_sources",
            "long_registered_device",
        ),
        minimum_decision="two_factor_required",
        requires_alert=True,
    ),
    AnchorCase(
        name="false_call_center",
        description="Falsa central",
        rule_names=("amount_far_above_baseline", "new_destination_above_usual_ceiling", "long_registered_device"),
        minimum_decision="two_factor_required",
        requires_alert=True,
    ),
)


def anchor_case_points(setting) -> int:
    if setting.rule.threshold_unit == "credibility_weight":
        return points_weighted_by_history(setting.points, ANCHOR_CASE_ACCEPTED_HISTORY_COUNT, setting.threshold)

    return setting.points


def anchor_case_outcome(anchor_case: AnchorCase, version, rules_by_name: dict) -> AnchorOutcome:
    settings_by_rule_name = {setting.rule.name: setting for setting in version.rule_settings}
    rule_hits = [
        RuleHit(rule_name, anchor_case_points(settings_by_rule_name[rule_name]), anchor_case.description)
        for rule_name in anchor_case.rule_names
        if settings_by_rule_name[rule_name].enabled
    ]
    analysis_decision = AnalysisDecision(rules_by_name)
    score_parts = analysis_decision.score_parts_of(rule_hits)
    risk_score = analysis_decision.risk_score(score_parts, version)

    return AnchorOutcome(
        decision=analysis_decision.decision_for_risk_score(risk_score, version),
        risk_score=risk_score,
        raises_alert=analysis_decision.destination_risk_score(score_parts) >= version.destination_risk_alert_threshold,
    )
