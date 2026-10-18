from decimal import ROUND_HALF_UP, Decimal

from psycopg2.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from dtos import risk_policy_response, risk_policy_templates_response
from errors import (
    ConcurrentRiskPolicyEdit,
    InconsistentRiskPolicy,
    RegulatoryRuleNotEditable,
    RepeatedRuleSetting,
    RiskPolicyVersionNotFound,
    RuleSettingNotApplicable,
    UnknownRule,
)
from models import Rule, RiskPolicyRuleSetting, RiskPolicyVersion
from repositories import RiskPolicyRepository, RuleRepository


BANK_POLICY_NAME = "bank"
TEMPLATE_POLICY_KIND = "template"
LARGEST_VERSION_DIGITS = 9
MINUTES_PER_DAY = 1440
DECIMAL_SETTING_PLACES = Decimal("0.01")
DECIMAL_SETTING_FIELDS = ("threshold", "company_threshold")


class RiskPolicyController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.risk_policy_repository = RiskPolicyRepository(self.context)
        self.rule_repository = RuleRepository(self.context)

    def get_current_bank_policy(self) -> dict:
        return risk_policy_response(self.risk_policy_repository.find_current_version(BANK_POLICY_NAME))

    def get_bank_policy_version(self, version: str) -> dict:
        if not version.isdigit() or len(version) > LARGEST_VERSION_DIGITS:
            raise RiskPolicyVersionNotFound()

        policy_version = self.risk_policy_repository.find_version(BANK_POLICY_NAME, int(version))

        if policy_version is None:
            raise RiskPolicyVersionNotFound()

        return risk_policy_response(policy_version)

    def get_templates(self) -> dict:
        return risk_policy_templates_response(self.risk_policy_repository.find_current_versions_of_kind(TEMPLATE_POLICY_KIND))

    def create_bank_policy_version(self, payload: dict) -> dict:
        rule_edits = self.validated_rule_edits(payload.get("rules", []), self.rule_repository.find_all_by_code())
        current_version = self.risk_policy_repository.find_current_version(BANK_POLICY_NAME)
        base_version = self.risk_policy_repository.find_current_version(payload.get("based_on_template", BANK_POLICY_NAME))

        new_version = RiskPolicyVersion(
            risk_policy=current_version.risk_policy,
            version=current_version.version + 1,
            based_on_version=base_version,
            change_reason=payload["change_reason"],
            **dict(base_version.parameters(), **payload.get("parameters", {})),
        )
        new_version.rule_settings = [
            self.edited_rule_setting(setting, rule_edits.get(setting.rule.code, {}))
            for setting in base_version.rule_settings
        ]
        self.ensure_consistent_policy(new_version)

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

    def validated_rule_edits(self, rule_edit_items: list, rules_by_code: dict) -> dict:
        rule_edits = {}

        for rule_edit_item in rule_edit_items:
            code = rule_edit_item["code"]

            if code in rule_edits:
                raise RepeatedRuleSetting(code)

            rule = rules_by_code.get(code)

            if rule is None:
                raise UnknownRule(code)

            if rule.kind == "regulatory":
                raise RegulatoryRuleNotEditable(code)

            setting_changes = {field: value for field, value in rule_edit_item.items() if field != "code"}

            for field in setting_changes:
                if not self.rule_accepts_setting(rule, field):
                    raise RuleSettingNotApplicable(code, field)

            rule_edits[code] = setting_changes

        return rule_edits

    @staticmethod
    def rule_accepts_setting(rule: Rule, field: str) -> bool:
        accepted_settings = {
            "enabled": True,
            "points": rule.kind in ("scoring", "reducer"),
            "threshold": rule.threshold_unit is not None,
            "window_minutes": rule.uses_window,
            "company_threshold": rule.uses_company_threshold,
        }
        return accepted_settings[field]

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
        settings_by_code = {setting.rule.code: setting for setting in version.rule_settings}

        if version.rejection_score_threshold <= version.two_factor_score_threshold:
            raise InconsistentRiskPolicy(
                "The rejection score threshold must be greater than the two factor score threshold.",
                "O limiar de reprovação precisa ser maior que o limiar de 2FA.",
            )

        for code, setting in settings_by_code.items():
            if setting.rule.kind == "scoring" and setting.points < 0:
                raise InconsistentRiskPolicy(
                    f"The scoring rule {code} cannot have negative points.",
                    f"A regra de pontuação {code} não pode ter pontos negativos.",
                )

            if setting.rule.kind == "reducer" and setting.points > 0:
                raise InconsistentRiskPolicy(
                    f"The reducer {code} cannot have positive points.",
                    f"O redutor {code} não pode ter pontos positivos.",
                )

        very_recent_account_days = settings_by_code["destination_account_opened_very_recently"].threshold
        recent_account_days = settings_by_code["destination_account_opened_recently"].threshold

        if very_recent_account_days >= recent_account_days:
            raise InconsistentRiskPolicy(
                "The very recent destination account range must be shorter than the recent destination account range.",
                "A faixa de conta de destino muito recente precisa ser menor que a de conta de destino recente.",
            )

        monthly_volume_window_minutes = settings_by_code["monthly_volume_above_typical"].window_minutes

        if monthly_volume_window_minutes >= version.history_window_days * MINUTES_PER_DAY:
            raise InconsistentRiskPolicy(
                "The monthly volume window must be shorter than the history window.",
                "A janela do volume mensal precisa ser menor que a janela de histórico.",
            )
