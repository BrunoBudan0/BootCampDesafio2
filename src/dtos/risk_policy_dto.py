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

    return {"name": version.risk_policy.name, "version": version.version}


def rule_setting_response(setting: RiskPolicyRuleSetting) -> dict:
    return {
        "code": setting.rule.code,
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
        "version": version.version,
        "change_reason": version.change_reason,
        "based_on": policy_reference(version.based_on_version),
        "parameters": version.parameters(),
        "rules": [rule_setting_response(setting) for setting in version.rule_settings],
    }


def risk_policy_templates_response(template_versions: list) -> dict:
    return {"templates": [risk_policy_response(version) for version in template_versions]}
