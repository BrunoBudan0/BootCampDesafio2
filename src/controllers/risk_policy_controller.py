import re
from decimal import ROUND_HALF_UP, Decimal

from psycopg2.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from controllers.rules import ANCHOR_CASES, anchor_case_outcome
from dtos import guardrails_response, risk_policy_response, risk_policy_templates_response
from errors import (
    AnchorCaseNoLongerCaught,
    ConcurrentRiskPolicyEdit,
    InconsistentRiskPolicy,
    OutsideSafetyRange,
    RegulatoryRuleNotEditable,
    RepeatedRuleSetting,
    RiskNotAcknowledged,
    RiskPolicyVersionNotFound,
    RuleSettingNotApplicable,
    UnknownRule,
)
from models import Rule, RiskPolicy, RiskPolicyGuardrail, RiskPolicyRuleSetting, RiskPolicyVersion
from repositories import RiskPolicyGuardrailRepository, RiskPolicyRepository, RuleRepository
from utils.money import brazilian_decimal


TEMPLATE_POLICY_KIND = "template"
REFERENCE_POLICY_NAME = "balanced"
VERSION_NUMBER_PATTERN = re.compile(r"[0-9]{1,9}")
MINUTES_PER_DAY = 1440
DECIMAL_SETTING_PLACES = Decimal("0.01")
DECIMAL_SETTING_FIELDS = ("threshold", "company_threshold")
WHOLE_UNIT_THRESHOLDS = ("count", "days")
LARGEST_THRESHOLD_IN_DAYS = 3650


class RiskPolicyController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.risk_policy_repository = RiskPolicyRepository(self.context)
        self.rule_repository = RuleRepository(self.context)
        self.risk_policy_guardrail_repository = RiskPolicyGuardrailRepository(self.context)

    def get_current_bank_policy(self) -> dict:
        return risk_policy_response(self.risk_policy_repository.find_current_version(RiskPolicy.BANK_NAME))

    def get_bank_policy_version(self, version_number_text: str) -> dict:
        if VERSION_NUMBER_PATTERN.fullmatch(version_number_text) is None:
            raise RiskPolicyVersionNotFound()

        policy_version = self.risk_policy_repository.find_version(RiskPolicy.BANK_NAME, int(version_number_text))

        if policy_version is None:
            raise RiskPolicyVersionNotFound()

        return risk_policy_response(policy_version)

    def get_templates(self) -> dict:
        return risk_policy_templates_response(self.risk_policy_repository.find_current_versions_of_kind(TEMPLATE_POLICY_KIND))

    def get_guardrails(self) -> dict:
        reference_version = self.risk_policy_repository.find_current_version(REFERENCE_POLICY_NAME)
        return guardrails_response(self.risk_policy_guardrail_repository.find_all(), reference_version, ANCHOR_CASES)

    def create_bank_policy_version(self, payload: dict) -> dict:
        rules_by_name = self.rule_repository.find_all_by_name()
        rule_edits = self.validated_rule_edits(payload.get("rules", []), rules_by_name)
        risk_acknowledged = payload.get("risk_acknowledged", False)
        current_version = self.risk_policy_repository.find_current_version(RiskPolicy.BANK_NAME)
        base_version = self.risk_policy_repository.find_current_version(payload.get("based_on_template", RiskPolicy.BANK_NAME))

        new_version = RiskPolicyVersion(
            risk_policy=current_version.risk_policy,
            version_number=current_version.version_number + 1,
            based_on_version=base_version,
            change_reason=payload["change_reason"],
            requested_by=payload.get("requested_by"),
            risk_acknowledged=risk_acknowledged,
            **dict(base_version.parameters(), **payload.get("parameters", {})),
        )
        new_version.rule_settings = [
            self.edited_rule_setting(setting, rule_edits.get(setting.rule.name, {}))
            for setting in base_version.rule_settings
        ]
        self.ensure_consistent_policy(new_version)
        self.ensure_within_guardrails(new_version, rules_by_name, risk_acknowledged)

        try:
            self.risk_policy_repository.add_version(new_version)
            response = risk_policy_response(new_version)
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            if isinstance(error.orig, UniqueViolation):
                raise ConcurrentRiskPolicyEdit()
            raise

        return response

    def ensure_within_guardrails(self, version: RiskPolicyVersion, rules_by_name: dict, risk_acknowledged: bool) -> None:
        reference_version = self.risk_policy_repository.find_current_version(REFERENCE_POLICY_NAME)
        loosened_settings = self.rules_switched_off_against_reference(version, reference_version)

        for guardrail in self.risk_policy_guardrail_repository.find_all():
            edited_value = guardrail.value_in(version)

            if loosens(guardrail, edited_value, guardrail.loosest_accepted_value):
                raise OutsideSafetyRange(
                    f"{guardrail.setting_name} = {brazilian_decimal(edited_value)} is beyond the safety limit of {brazilian_decimal(guardrail.loosest_accepted_value)}.",
                    f"{guardrail.setting_name} = {brazilian_decimal(edited_value)} passa do limite de segurança de {brazilian_decimal(guardrail.loosest_accepted_value)}.",
                )

            if loosens(guardrail, edited_value, guardrail.value_in(reference_version)):
                loosened_settings.append(guardrail.setting_name)

        missed_anchor_cases = [
            anchor_case for anchor_case in ANCHOR_CASES if not anchor_case_outcome(anchor_case, version, rules_by_name).reaches_the_minimum_of(anchor_case)
        ]

        if missed_anchor_cases:
            raise AnchorCaseNoLongerCaught(missed_anchor_cases)

        if loosened_settings and not risk_acknowledged:
            raise RiskNotAcknowledged(loosened_settings)

    @staticmethod
    def rules_switched_off_against_reference(version: RiskPolicyVersion, reference_version: RiskPolicyVersion) -> list:
        enabled_in_reference = {setting.rule.name: setting.enabled for setting in reference_version.rule_settings}
        switched_off = []

        for setting in version.rule_settings:
            rule_name = setting.rule.name

            if setting.enabled or not enabled_in_reference[rule_name] or setting.rule.kind == "reducer":
                continue

            if setting.rule.kind == "eliminatory":
                raise OutsideSafetyRange(
                    f"The eliminatory rule {rule_name} cannot be disabled.",
                    f"A regra eliminatória {rule_name} não pode ser desligada.",
                )

            switched_off.append(f"{rule_name}.enabled")

        return switched_off

    def validated_rule_edits(self, rule_edit_items: list, rules_by_name: dict) -> dict:
        rule_edits = {}

        for rule_edit_item in rule_edit_items:
            rule_name = rule_edit_item["code"]

            if rule_name in rule_edits:
                raise RepeatedRuleSetting(rule_name)

            rule = rules_by_name.get(rule_name)

            if rule is None:
                raise UnknownRule(rule_name)

            if rule.kind == "regulatory":
                raise RegulatoryRuleNotEditable(rule_name)

            setting_changes = {field: value for field, value in rule_edit_item.items() if field != "code"}

            for field, value in setting_changes.items():
                if not self.rule_accepts_setting(rule, field):
                    raise RuleSettingNotApplicable(rule_name, field)

                if field in DECIMAL_SETTING_FIELDS and not self.rule_accepts_setting_value(rule, field, value):
                    raise RuleSettingNotApplicable(rule_name, field, value)

            rule_edits[rule_name] = setting_changes

        return rule_edits

    @staticmethod
    def rule_accepts_setting(rule: Rule, field: str) -> bool:
        accepted_settings = {
            "enabled": True,
            "points": rule.kind in ("scoring", "reducer"),
            "threshold": rule.threshold_unit is not None,
            "window_minutes": rule.uses_window_minutes,
            "company_threshold": rule.uses_company_threshold,
        }
        return accepted_settings[field]

    @staticmethod
    def rule_accepts_setting_value(rule: Rule, field: str, value) -> bool:
        decimal_value = Decimal(str(value))

        if decimal_value != decimal_value.quantize(DECIMAL_SETTING_PLACES):
            return False

        if field == "threshold" and rule.threshold_unit == "days" and decimal_value > LARGEST_THRESHOLD_IN_DAYS:
            return False

        counts_whole_units = field == "company_threshold" or rule.threshold_unit in WHOLE_UNIT_THRESHOLDS
        return not counts_whole_units or decimal_value == decimal_value.to_integral_value()

    @staticmethod
    def edited_rule_setting(base_setting: RiskPolicyRuleSetting, setting_changes: dict) -> RiskPolicyRuleSetting:
        setting_values = {field: getattr(base_setting, field) for field in RiskPolicyRuleSetting.EDITABLE_FIELDS}

        for field, value in setting_changes.items():
            if field in DECIMAL_SETTING_FIELDS:
                value = Decimal(str(value)).quantize(DECIMAL_SETTING_PLACES, rounding=ROUND_HALF_UP)
            setting_values[field] = value

        return RiskPolicyRuleSetting(rule=base_setting.rule, **setting_values)

    @staticmethod
    def ensure_consistent_policy(version: RiskPolicyVersion) -> None:
        settings_by_rule_name = {setting.rule.name: setting for setting in version.rule_settings}

        if version.rejection_score_threshold <= version.two_factor_score_threshold:
            raise InconsistentRiskPolicy(
                "The rejection score threshold must be greater than the two factor score threshold.",
                "O limiar de reprovação precisa ser maior que o limiar de 2FA.",
            )

        if version.counterparty_relationship_cap > version.counterparty_family_cap:
            raise InconsistentRiskPolicy(
                "The relationship cap cannot be greater than the counterparty family cap.",
                "O teto da relação não pode ser maior que o teto da família contraparte.",
            )

        for rule_name, setting in settings_by_rule_name.items():
            if setting.rule.kind == "scoring" and setting.points < 0:
                raise InconsistentRiskPolicy(
                    f"The scoring rule {rule_name} cannot have negative points.",
                    f"A regra de pontuação {rule_name} não pode ter pontos negativos.",
                )

            if setting.rule.kind == "reducer" and setting.points > 0:
                raise InconsistentRiskPolicy(
                    f"The reducer {rule_name} cannot have positive points.",
                    f"O redutor {rule_name} não pode ter pontos positivos.",
                )

        very_recent_account_days = settings_by_rule_name["destination_account_opened_very_recently"].threshold
        recent_account_days = settings_by_rule_name["destination_account_opened_recently"].threshold

        if very_recent_account_days >= recent_account_days:
            raise InconsistentRiskPolicy(
                "The very recent destination account range must be shorter than the recent destination account range.",
                "A faixa de conta de destino muito recente precisa ser menor que a de conta de destino recente.",
            )

        above_baseline_multiplier = settings_by_rule_name["amount_above_baseline"].threshold
        far_above_baseline_multiplier = settings_by_rule_name["amount_far_above_baseline"].threshold

        if far_above_baseline_multiplier <= above_baseline_multiplier:
            raise InconsistentRiskPolicy(
                "The far above baseline multiplier must be greater than the above baseline multiplier.",
                "O multiplicador do valor muito fora do padrão precisa ser maior que o do valor fora do padrão.",
            )

        monthly_volume_window_minutes = settings_by_rule_name["monthly_volume_above_typical"].window_minutes

        if monthly_volume_window_minutes >= version.history_window_days * MINUTES_PER_DAY:
            raise InconsistentRiskPolicy(
                "The monthly volume window must be shorter than the history window.",
                "A janela do volume mensal precisa ser menor que a janela de histórico.",
            )


def loosens(guardrail: RiskPolicyGuardrail, edited_value, compared_value) -> bool:
    if edited_value is None or compared_value is None:
        return False

    if guardrail.loosening_direction == "higher":
        return edited_value > compared_value

    return edited_value < compared_value
