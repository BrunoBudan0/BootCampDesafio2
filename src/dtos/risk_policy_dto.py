from decimal import Decimal
from typing import Optional, Union

from models import RiskPolicyRuleSetting, RiskPolicyVersion


def decimal_to_json_number(value: Optional[Decimal]) -> Optional[Union[int, float]]:
    if value is None:
        return None

    if value == value.to_integral_value():
        return int(value)

    return float(value)


def policy_reference(version: Optional[RiskPolicyVersion]) -> Optional[dict]:
    if version is None:
        return None

    return {"name": version.risk_policy.name, "version": version.version_number}


def rule_setting_response(setting: RiskPolicyRuleSetting) -> dict:
    return {
        "code": setting.rule.name,
        "kind": setting.rule.kind,
        "family": setting.rule.family,
        "enabled": setting.enabled,
        "points": setting.points,
        "threshold": decimal_to_json_number(setting.threshold),
        "window_minutes": setting.window_minutes,
        "company_threshold": decimal_to_json_number(setting.company_threshold),
    }


def risk_policy_response(version: RiskPolicyVersion) -> dict:
    return {
        "name": version.risk_policy.name,
        "version": version.version_number,
        "change_reason": version.change_reason,
        "requested_by": version.requested_by,
        "risk_acknowledged": version.risk_acknowledged,
        "based_on": policy_reference(version.based_on_version),
        "parameters": version.parameters(),
        "rules": [rule_setting_response(setting) for setting in version.rule_settings],
    }


def risk_policy_templates_response(template_versions: list) -> dict:
    return {"templates": [risk_policy_response(version) for version in template_versions]}


def setting_value_response(value):
    if isinstance(value, Decimal):
        return decimal_to_json_number(value)

    return value


def guardrails_response(guardrails: list, reference_version: RiskPolicyVersion, anchor_cases: tuple) -> dict:
    return {
        "reference": policy_reference(reference_version),
        "guardrails": [
            {
                "setting": guardrail.setting_name,
                "loosens_when": guardrail.loosening_direction,
                "recommended": setting_value_response(guardrail.value_in(reference_version)),
                "loosest_accepted_value": setting_value_response(guardrail.loosest_accepted_value),
            }
            for guardrail in guardrails
        ],
        "anchor_cases": [
            {
                "code": anchor_case.name,
                "description": anchor_case.description,
                "rules": list(anchor_case.rule_names),
                "minimum_decision": anchor_case.minimum_decision,
                "requires_alert": anchor_case.requires_alert,
            }
            for anchor_case in anchor_cases
        ],
    }
