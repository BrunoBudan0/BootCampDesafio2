from dataclasses import dataclass

from controllers.rules.catalog import RuleHit
from controllers.rules.credibility import points_weighted_by_history
from controllers.rules.decision import SEVERITY, AnalysisDecision


ANCHOR_HISTORY_COUNT = 20


@dataclass(frozen=True)
class AnchorCase:
    code: str
    description: str
    rule_codes: tuple
    minimum_decision: str
    requires_alert: bool


@dataclass(frozen=True)
class AnchorOutcome:
    decision: str
    risk_score: int
    raises_alert: bool

    def meets(self, anchor_case: AnchorCase) -> bool:
        reaches_the_decision = SEVERITY[self.decision] >= SEVERITY[anchor_case.minimum_decision]
        return reaches_the_decision and (self.raises_alert or not anchor_case.requires_alert)


ANCHOR_CASES = (
    AnchorCase(
        code="account_takeover_with_high_amount",
        description="Invasão de conta com valor alto",
        rule_codes=("ip_unfamiliar", "location_unfamiliar", "channel_unfamiliar", "amount_far_above_baseline", "new_destination_above_usual_ceiling"),
        minimum_decision="rejected",
        requires_alert=False,
    ),
    AnchorCase(
        code="mule_flagged_by_the_base",
        description="Laranja marcado pela base",
        rule_codes=(
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
        code="false_call_center",
        description="Falsa central",
        rule_codes=("amount_far_above_baseline", "new_destination_above_usual_ceiling", "long_registered_device"),
        minimum_decision="two_factor_required",
        requires_alert=True,
    ),
)


def anchor_case_points(setting) -> int:
    if setting.rule.threshold_unit == "credibility_weight":
        return points_weighted_by_history(setting.points, ANCHOR_HISTORY_COUNT, setting.threshold)

    return setting.points


def anchor_case_outcome(anchor_case: AnchorCase, version, rules_by_code: dict) -> AnchorOutcome:
    settings_by_code = {setting.rule.code: setting for setting in version.rule_settings}
    rule_hits = [
        RuleHit(code, anchor_case_points(settings_by_code[code]), anchor_case.description)
        for code in anchor_case.rule_codes
        if settings_by_code[code].enabled
    ]
    decision = AnalysisDecision(rules_by_code)
    parts = decision.score_parts(rule_hits)
    risk_score = decision.risk_score(parts, version)

    return AnchorOutcome(
        decision=decision.score_band(risk_score, version),
        risk_score=risk_score,
        raises_alert=decision.destination_risk(parts) >= version.destination_alert_threshold,
    )
