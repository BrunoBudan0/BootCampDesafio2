from errors.base_error import QIException


class RiskPolicyVersionNotFound(QIException):
    code = "QIT001011"

    def __init__(self) -> None:
        title = "Risk Policy Version Not Found"
        http_status = 404
        description = "The requested version of the bank risk policy does not exist."
        translation = "A versão pedida da política de risco do banco não existe."
        super().__init__(title, self.code, http_status, description, translation)


class UnknownRule(QIException):
    code = "QIT001012"

    def __init__(self, rule_name: str) -> None:
        title = "Unknown Rule"
        http_status = 422
        description = f"The rule {rule_name} is not part of the rule catalog."
        translation = f"A regra {rule_name} não faz parte do catálogo de regras."
        super().__init__(title, self.code, http_status, description, translation)


class RegulatoryRuleNotEditable(QIException):
    code = "QIT001013"

    def __init__(self, rule_name: str) -> None:
        title = "Regulatory Rule Not Editable"
        http_status = 422
        description = f"The rule {rule_name} comes from a BCB regulation and its values cannot be edited."
        translation = f"A regra {rule_name} vem de norma do BCB e os valores dela não podem ser editados."
        super().__init__(title, self.code, http_status, description, translation)


class RuleSettingNotApplicable(QIException):
    code = "QIT001014"

    def __init__(self, rule_name: str, setting_name: str, refused_value=None) -> None:
        title = "Rule Setting Not Applicable"
        http_status = 422
        if refused_value is None:
            description = f"The rule {rule_name} does not use the setting {setting_name}."
            translation = f"A regra {rule_name} não usa o ajuste {setting_name}."
        else:
            description = f"The rule {rule_name} does not accept {refused_value} as {setting_name}: whole units for counts and days, at most 2 decimal places otherwise."
            translation = f"A regra {rule_name} não aceita {refused_value} em {setting_name}: contagens e dias são inteiros, e os demais limites têm no máximo 2 casas."
        super().__init__(title, self.code, http_status, description, translation)


class RepeatedRuleSetting(QIException):
    code = "QIT001015"

    def __init__(self, rule_name: str) -> None:
        title = "Repeated Rule Setting"
        http_status = 422
        description = f"The rule {rule_name} appears more than once in the edit."
        translation = f"A regra {rule_name} aparece mais de uma vez na edição."
        super().__init__(title, self.code, http_status, description, translation)


class InconsistentRiskPolicy(QIException):
    code = "QIT001016"

    def __init__(self, description: str, translation: str) -> None:
        title = "Inconsistent Risk Policy"
        http_status = 422
        super().__init__(title, self.code, http_status, description, translation)


class ConcurrentRiskPolicyEdit(QIException):
    code = "QIT001017"

    def __init__(self) -> None:
        title = "Concurrent Risk Policy Edit"
        http_status = 409
        description = "Another edit created this version of the bank risk policy first. Read the current version and try again."
        translation = "Outra edição criou esta versão da política de risco do banco antes. Leia a versão vigente e tente de novo."
        super().__init__(title, self.code, http_status, description, translation)


class PixAnalysisNotFound(QIException):
    code = "QIT001001"

    def __init__(self, pix_id: str) -> None:
        title = "Pix Analysis Not Found"
        http_status = 404
        description = f"There is no analysis for the Pix {pix_id}."
        translation = f"Não existe análise para o Pix {pix_id}."
        super().__init__(title, self.code, http_status, description, translation)


class PixIdUsedWithOtherContent(QIException):
    code = "QIT001002"

    def __init__(self, pix_id: str) -> None:
        title = "Pix Id Used With Other Content"
        http_status = 409
        description = f"The Pix {pix_id} was already analyzed with different content."
        translation = f"O Pix {pix_id} já foi analisado com outro conteúdo."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidDocumentNumber(QIException):
    code = "QIT001003"

    def __init__(self, field_name: str) -> None:
        title = "Invalid Document Number"
        http_status = 422
        description = f"The document in {field_name} is not a valid CPF or CNPJ."
        translation = f"O documento em {field_name} não é um CPF ou CNPJ válido."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidDate(QIException):
    code = "QIT001004"

    def __init__(self, field_name: str) -> None:
        title = "Invalid Date"
        http_status = 422
        description = f"The date in {field_name} does not exist or has a UTC offset outside -12:00 to +14:00."
        translation = f"A data em {field_name} não existe ou tem fuso fora de -12:00 a +14:00."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidIpAddress(QIException):
    code = "QIT001005"

    def __init__(self) -> None:
        title = "Invalid IP Address"
        http_status = 422
        description = "The source ip is not a valid IPv4 or IPv6 address."
        translation = "O IP de origem não é um IPv4 nem um IPv6 válido."
        super().__init__(title, self.code, http_status, description, translation)


class AccountOpenedAfterTransaction(QIException):
    code = "QIT001006"

    def __init__(self, account_name: str) -> None:
        title = "Account Opened After Transaction"
        http_status = 422
        description = f"The {account_name} was opened after the Pix transaction date."
        translation = f"A conta em {account_name} foi aberta depois da data do Pix."
        super().__init__(title, self.code, http_status, description, translation)


class TwoFactorNotRequested(QIException):
    code = "QIT001007"

    def __init__(self, pix_id: str) -> None:
        title = "Two Factor Not Requested"
        http_status = 409
        description = f"The analysis of the Pix {pix_id} did not ask for two factor authentication."
        translation = f"A análise do Pix {pix_id} não pediu 2FA."
        super().__init__(title, self.code, http_status, description, translation)


class TwoFactorAlreadyAnswered(QIException):
    code = "QIT001008"

    def __init__(self, pix_id: str, recorded_result: str) -> None:
        title = "Two Factor Already Answered"
        http_status = 409
        description = f"The two factor of the Pix {pix_id} was already recorded as {recorded_result}."
        translation = f"O 2FA do Pix {pix_id} já foi registrado como {recorded_result}."
        super().__init__(title, self.code, http_status, description, translation)


class TwoFactorOutsideValidity(QIException):
    code = "QIT001009"

    def __init__(self, pix_id: str) -> None:
        title = "Two Factor Outside Validity"
        http_status = 422
        description = f"The confirmation of the Pix {pix_id} is before the Pix or after the two factor expiration."
        translation = f"A confirmação do Pix {pix_id} é anterior ao Pix ou posterior ao vencimento do 2FA."
        super().__init__(title, self.code, http_status, description, translation)


class OutsideSafetyRange(QIException):
    code = "QIT001018"

    def __init__(self, description: str, translation: str) -> None:
        title = "Outside Safety Range"
        http_status = 422
        super().__init__(title, self.code, http_status, description, translation)


class AnchorCaseNoLongerCaught(QIException):
    code = "QIT001019"

    def __init__(self, missed_anchor_cases: list) -> None:
        title = "Anchor Case No Longer Caught"
        http_status = 422
        cases = "; ".join(
            f"{anchor_case.description} (mínimo {anchor_case.minimum_decision}{' com alerta' if anchor_case.requires_alert else ''})"
            for anchor_case in missed_anchor_cases
        )
        description = f"With this policy, these anchor cases would no longer reach their minimum decision: {cases}."
        translation = f"Com esta política, estes casos-âncora deixariam de chegar à decisão mínima: {cases}."
        super().__init__(title, self.code, http_status, description, translation)


class RiskNotAcknowledged(QIException):
    code = "QIT001020"

    def __init__(self, loosened_settings: list) -> None:
        title = "Risk Not Acknowledged"
        http_status = 422
        settings = ", ".join(loosened_settings)
        description = f"This edit loosens the policy compared with the reference ({settings}). Send risk_acknowledged and requested_by to confirm it."
        translation = f"Esta edição afrouxa a política em relação à referência ({settings}). Envie risk_acknowledged e requested_by para confirmar."
        super().__init__(title, self.code, http_status, description, translation)


class NightlyLimitOnlyForIndividuals(QIException):
    code = "QIT001010"

    def __init__(self) -> None:
        title = "Nightly Limit Only For Individuals"
        http_status = 422
        description = "The nightly limit of the regulation applies only to individuals (CPF)."
        translation = "O limite noturno da norma vale só para pessoa física (CPF)."
        super().__init__(title, self.code, http_status, description, translation)
