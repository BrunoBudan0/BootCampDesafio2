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

    def __init__(self, rule_code: str) -> None:
        title = "Unknown Rule"
        http_status = 422
        description = f"The rule {rule_code} is not part of the rule catalog."
        translation = f"A regra {rule_code} não faz parte do catálogo de regras."
        super().__init__(title, self.code, http_status, description, translation)


class RegulatoryRuleNotEditable(QIException):
    code = "QIT001013"

    def __init__(self, rule_code: str) -> None:
        title = "Regulatory Rule Not Editable"
        http_status = 422
        description = f"The rule {rule_code} comes from a BCB regulation and its values cannot be edited."
        translation = f"A regra {rule_code} vem de norma do BCB e os valores dela não podem ser editados."
        super().__init__(title, self.code, http_status, description, translation)


class RuleSettingNotApplicable(QIException):
    code = "QIT001014"

    def __init__(self, rule_code: str, setting_name: str, refused_value=None) -> None:
        title = "Rule Setting Not Applicable"
        http_status = 422
        if refused_value is None:
            description = f"The rule {rule_code} does not use the setting {setting_name}."
            translation = f"A regra {rule_code} não usa o ajuste {setting_name}."
        else:
            description = f"The rule {rule_code} does not accept {refused_value} as {setting_name}: whole units for counts and days, at most 2 decimal places otherwise."
            translation = f"A regra {rule_code} não aceita {refused_value} em {setting_name}: contagens e dias são inteiros, e os demais limites têm no máximo 2 casas."
        super().__init__(title, self.code, http_status, description, translation)


class RepeatedRuleSetting(QIException):
    code = "QIT001015"

    def __init__(self, rule_code: str) -> None:
        title = "Repeated Rule Setting"
        http_status = 422
        description = f"The rule {rule_code} appears more than once in the edit."
        translation = f"A regra {rule_code} aparece mais de uma vez na edição."
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
