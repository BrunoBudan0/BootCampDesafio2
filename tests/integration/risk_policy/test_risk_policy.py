from datetime import timedelta

import pytest

from tests.utils.assertions import assert_error, assert_rule_fired, assert_rule_not_fired, fired_rule_hit
from tests.utils.clock import business_hours_today
from tests.utils.pix_payload import (
    new_company_payee,
    new_company_payer,
    new_individual_payee,
    new_individual_payer,
    pix_payload,
    same_payee_in_another_account,
)
from tests.utils.request_generator import RequestGenerator
from tests.utils.requisition import ClientRequisition
from tests.utils.scenario import (
    analyze,
    current_bank_policy,
    edit_bank_policy,
    send_all_at_the_same_time,
    payer_with_accepted_history,
    restore_balanced_bank_policy,
)


POLICY_FIELDS = {"name", "version", "change_reason", "requested_by", "risk_acknowledged", "based_on", "parameters", "rules"}
RISK_ACKNOWLEDGEMENT = {"requested_by": "analista.risco@banco.com.br", "risk_acknowledged": True}
RULE_SETTING_FIELDS = {"code", "kind", "family", "enabled", "points", "threshold", "window_minutes", "company_threshold"}
POLICY_PARAMETER_NAMES = {
    "history_window_days",
    "source_baseline_reference_weight",
    "population_median_reference_weight",
    "reference_average_ticket_individual_to_individual_cents",
    "reference_average_ticket_individual_to_company_cents",
    "reference_average_ticket_company_to_individual_cents",
    "reference_average_ticket_company_to_company_cents",
    "amount_rules_floor_cents",
    "new_account_age_days",
    "new_account_cap_individual_cents",
    "new_account_cap_company_cents",
    "identity_family_cap",
    "velocity_family_cap",
    "amount_family_cap",
    "counterparty_family_cap",
    "counterparty_relationship_cap",
    "behavior_score_cap",
    "two_factor_score_threshold",
    "rejection_score_threshold",
    "two_factor_validity_minutes",
    "destination_risk_alert_threshold",
    "short_term_window_minutes",
}
EDITABLE_RULES = {
    "device_used_by_many_sources",
    "impossible_travel_on_unregistered_device",
    "new_account_to_new_destination_far_above_cap",
    "impossible_travel",
    "ip_unfamiliar",
    "location_unfamiliar",
    "channel_unfamiliar",
    "two_factor_denied_recently",
    "new_account_above_cap",
    "burst_of_pix",
    "amount_above_baseline",
    "amount_far_above_baseline",
    "monthly_volume_above_typical",
    "destination_account_opened_very_recently",
    "destination_account_opened_recently",
    "new_destination_above_usual_ceiling",
    "destination_receiving_from_many_sources",
    "destination_rejected_for_other_sources",
    "destination_document_in_many_accounts",
    "same_owner",
    "known_destination",
    "long_registered_device",
}
BALANCED_PARAMETERS = {
    "history_window_days": 90,
    "source_baseline_reference_weight": 5,
    "population_median_reference_weight": 30,
    "reference_average_ticket_individual_to_individual_cents": 26864,
    "reference_average_ticket_individual_to_company_cents": 11242,
    "reference_average_ticket_company_to_individual_cents": 54958,
    "reference_average_ticket_company_to_company_cents": 540453,
    "amount_rules_floor_cents": 10000,
    "new_account_age_days": 30,
    "new_account_cap_individual_cents": 100000,
    "new_account_cap_company_cents": 1000000,
    "identity_family_cap": 50,
    "velocity_family_cap": 40,
    "amount_family_cap": 35,
    "counterparty_family_cap": 70,
    "counterparty_relationship_cap": 30,
    "behavior_score_cap": 65,
    "two_factor_score_threshold": 40,
    "rejection_score_threshold": 70,
    "two_factor_validity_minutes": 10,
    "destination_risk_alert_threshold": 30,
    "short_term_window_minutes": 1440,
}


@pytest.fixture
def restore_bank_policy():
    yield
    restore_balanced_bank_policy()


def find_rule_setting(policy, rule_code):
    for setting in policy["rules"]:
        if setting["code"] == rule_code:
            return setting
    raise AssertionError(f"A política não traz o ajuste da regra {rule_code}")


def find_template(name):
    status, body = RequestGenerator.GET_risk_policy_templates()
    assert status == 200
    for policy in body["templates"]:
        if policy["name"] == name:
            return policy
    raise AssertionError(f"O modelo {name} não existe")


def assert_policy_unchanged(version_before):
    assert current_bank_policy()["version"] == version_before


class TestReadRiskPolicy:
    def test_current_policy_shows_parameters_and_editable_rules(self):
        status, body = RequestGenerator.GET_risk_policy()

        assert status == 200
        assert set(body) == POLICY_FIELDS
        assert body["name"] == "bank"
        assert set(body["parameters"]) == POLICY_PARAMETER_NAMES
        assert {setting["code"] for setting in body["rules"]} == EDITABLE_RULES
        assert all(set(setting) == RULE_SETTING_FIELDS for setting in body["rules"])

    def test_regulatory_rules_are_not_part_of_the_policy(self):
        policy = current_bank_policy()

        rule_codes_in_policy = {setting["code"] for setting in policy["rules"]}
        assert "nightly_limit_exceeded" not in rule_codes_in_policy
        assert "unregistered_device_limit_exceeded" not in rule_codes_in_policy

    def test_templates_differ_in_thresholds_amount_multipliers_and_behavior_cap(self):
        multipliers = {
            name: (
                find_rule_setting(find_template(name), "amount_above_baseline")["threshold"],
                find_rule_setting(find_template(name), "amount_far_above_baseline")["threshold"],
            )
            for name in ("conservative", "balanced", "permissive")
        }

        assert multipliers == {"conservative": (3, 10), "balanced": (5, 20), "permissive": (10, 40)}
        assert find_template("balanced")["parameters"] == BALANCED_PARAMETERS
        assert find_template("conservative")["parameters"] == dict(
            BALANCED_PARAMETERS, two_factor_score_threshold=35, rejection_score_threshold=60, destination_risk_alert_threshold=25, behavior_score_cap=105
        )
        assert find_template("permissive")["parameters"] == dict(
            BALANCED_PARAMETERS, two_factor_score_threshold=45, rejection_score_threshold=80, behavior_score_cap=75
        )

    def test_bank_policy_follows_the_balanced_template(self):
        policy = current_bank_policy()
        balanced = find_template("balanced")

        assert policy["parameters"] == balanced["parameters"]
        assert sorted(policy["rules"], key=lambda setting: setting["code"]) == sorted(balanced["rules"], key=lambda setting: setting["code"])

    def test_unknown_version_is_refused_with_404(self):
        for unknown_version in ("999999", "zero", "-1", "²", "1" * 20):
            status, body = RequestGenerator.GET_risk_policy_version(unknown_version)

            assert_error(status, body, 404, "QIT001011")

    def test_policy_without_internal_token_is_refused_with_403(self):
        response = ClientRequisition.send("GET", "/risk-policy")

        assert_error(response.response_status, response.response_json, 403, "QIT000002")


class TestEditRiskPolicy:
    def test_new_version_changes_what_was_sent_and_inherits_the_rest(self, restore_bank_policy):
        before = current_bank_policy()

        status, body = RequestGenerator.POST_risk_policy_version(
            {
                "change_reason": "Baixa o limiar de 2FA",
                "parameters": {"two_factor_score_threshold": 35},
                "rules": [{"code": "burst_of_pix", "points": 30}],
            }
        )

        assert status == 201
        assert body["version"] == before["version"] + 1
        assert body["based_on"] == {"name": "bank", "version": before["version"]}
        assert body["change_reason"] == "Baixa o limiar de 2FA"
        assert body["parameters"] == dict(before["parameters"], two_factor_score_threshold=35)
        assert find_rule_setting(body, "burst_of_pix") == dict(find_rule_setting(before, "burst_of_pix"), points=30)
        assert current_bank_policy() == body

    def test_decimal_threshold_is_returned_as_saved(self, restore_bank_policy):
        created = edit_bank_policy(
            {"change_reason": "Multiplicador entre o equilibrado e o conservador", "rules": [{"code": "amount_above_baseline", "threshold": 4.5}]},
            "editar o multiplicador",
        )

        assert find_rule_setting(created, "amount_above_baseline")["threshold"] == 4.5
        assert find_rule_setting(current_bank_policy(), "amount_above_baseline")["threshold"] == 4.5

    def test_ten_years_is_accepted_as_a_threshold_in_days_and_pix_keep_being_analyzed(self, restore_bank_policy):
        created = edit_bank_policy(
            {"change_reason": "Aparelho só abate depois de 10 anos", "rules": [{"code": "long_registered_device", "threshold": 3650}]},
            "editar o prazo do aparelho cadastrado",
        )

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today()))

        assert find_rule_setting(created, "long_registered_device")["threshold"] == 3650
        assert analysis["metadata"]["policy"]["version"] == created["version"]

    def test_old_version_stays_readable_and_unchanged(self, restore_bank_policy):
        before = current_bank_policy()
        edit_bank_policy({"change_reason": "Muda a validade do 2FA", "parameters": {"two_factor_validity_minutes": 5}}, "editar a política")

        status, old_version = RequestGenerator.GET_risk_policy_version(before["version"])

        assert status == 200
        assert old_version == before

    def test_version_based_on_a_template_copies_the_template(self, restore_bank_policy):
        edit_bank_policy({"change_reason": "Ajusta antes de trocar de modelo", "parameters": {"two_factor_score_threshold": 38}}, "editar a política")

        status, body = RequestGenerator.POST_risk_policy_version({"change_reason": "Passa a seguir o modelo conservador", "based_on_template": "conservative"})

        assert status == 201
        assert body["based_on"] == {"name": "conservative", "version": 1}
        assert body["parameters"]["two_factor_score_threshold"] == 35
        assert find_rule_setting(body, "amount_above_baseline")["threshold"] == 3
        assert find_rule_setting(body, "amount_far_above_baseline")["threshold"] == 10

    def test_new_analyses_record_the_new_version(self, restore_bank_policy):
        edited = edit_bank_policy({"change_reason": "Versão para conferir a análise", "parameters": {"destination_risk_alert_threshold": 25}}, "editar a política")

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today()))

        assert analysis["metadata"]["policy"] == {"name": "bank", "version": edited["version"]}

    def test_disabled_rule_stops_firing(self, restore_bank_policy):
        transaction_date = business_hours_today()
        edit_bank_policy(
            {"change_reason": "Desliga a conta de destino muito recente", "rules": [{"code": "destination_account_opened_very_recently", "enabled": False}], **RISK_ACKNOWLEDGEMENT},
            "desligar a regra",
        )

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(opening_date=transaction_date - timedelta(days=3)), transaction_date))

        assert_rule_not_fired(analysis, "destination_account_opened_very_recently")

    def test_edited_points_are_the_points_of_the_hit(self, restore_bank_policy):
        transaction_date = business_hours_today()
        edit_bank_policy(
            {"change_reason": "Aumenta o peso da conta de destino muito recente", "rules": [{"code": "destination_account_opened_very_recently", "points": 35}]},
            "editar os pontos",
        )

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(opening_date=transaction_date - timedelta(days=3)), transaction_date))

        assert fired_rule_hit(analysis, "destination_account_opened_very_recently")["points"] == 35

    def test_conservative_multiplier_flags_an_amount_the_balanced_accepts(self, restore_bank_policy):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 15)
        under_balanced = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 45000))
        edit_bank_policy({"change_reason": "Passa a seguir o modelo conservador", "based_on_template": "conservative"}, "trocar de modelo")

        under_conservative = analyze(pix_payload(payer, new_individual_payee(), transaction_date + timedelta(minutes=1), 45000))

        assert_rule_not_fired(under_balanced, "amount_above_baseline")
        assert_rule_fired(under_conservative, "amount_above_baseline")

    def test_raised_amount_floor_silences_the_amount_rules(self, restore_bank_policy):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)
        edit_bank_policy({"change_reason": "Piso das regras de valor em R$ 5.000", "parameters": {"amount_rules_floor_cents": 500000}, **RISK_ACKNOWLEDGEMENT}, "subir o piso")

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 200000))

        assert_rule_not_fired(analysis, "amount_above_baseline")
        assert_rule_not_fired(analysis, "amount_far_above_baseline")

    def test_amount_floor_is_compared_with_the_accumulated_amount(self, restore_bank_policy):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)
        edit_bank_policy({"change_reason": "Piso das regras de valor em R$ 5.000", "parameters": {"amount_rules_floor_cents": 500000}, **RISK_ACKNOWLEDGEMENT}, "subir o piso")
        payee = new_individual_payee()
        analyze(pix_payload(payer, payee, transaction_date, 300000))

        analysis = analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=1), 300000))

        assert_rule_fired(analysis, "amount_far_above_baseline")

    def test_shorter_monthly_volume_window_is_compared_with_a_typical_volume_of_the_same_length(self, restore_bank_policy):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=50), 2, spacing=timedelta(days=30))
        edit_bank_policy(
            {"change_reason": "Volume comparado em 15 dias", "rules": [{"code": "monthly_volume_above_typical", "window_minutes": 21600}]},
            "encurtar a janela do volume",
        )

        analysis = analyze(pix_payload(payer, payee, transaction_date, 15000))

        assert_rule_fired(analysis, "monthly_volume_above_typical")

    def test_raised_amount_floor_also_silences_the_new_destination_ceiling(self, restore_bank_policy):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)
        edit_bank_policy({"change_reason": "Piso das regras de valor em R$ 5.000", "parameters": {"amount_rules_floor_cents": 500000}, **RISK_ACKNOWLEDGEMENT}, "subir o piso")

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 200000))

        assert_rule_not_fired(analysis, "new_destination_above_usual_ceiling")

    def test_company_threshold_of_the_burst_is_the_limit_for_company_payers(self, restore_bank_policy):
        first_moment = business_hours_today()
        edit_bank_policy(
            {"change_reason": "Rajada de PJ com o mesmo limite da PF", "rules": [{"code": "burst_of_pix", "company_threshold": 5}]},
            "editar o limite de PJ da rajada",
        )
        company = new_company_payer()
        for minute in range(4):
            analyze(pix_payload(company, new_individual_payee(), first_moment + timedelta(minutes=minute)))

        analysis = analyze(pix_payload(company, new_individual_payee(), first_moment + timedelta(minutes=4)))

        assert_rule_fired(analysis, "burst_of_pix")

    def test_company_threshold_is_the_limit_for_company_destinations(self, restore_bank_policy):
        transaction_date = business_hours_today()
        edit_bank_policy(
            {"change_reason": "PJ com o mesmo limite de contas da PF", "rules": [{"code": "destination_document_in_many_accounts", "company_threshold": 3}]},
            "editar o limite de PJ",
        )
        payee = new_company_payee()
        for minutes_ago in (31, 30):
            analyze(pix_payload(new_individual_payer(), same_payee_in_another_account(payee), transaction_date - timedelta(minutes=minutes_ago)))

        analysis = analyze(pix_payload(new_individual_payer(), same_payee_in_another_account(payee), transaction_date))

        assert_rule_fired(analysis, "destination_document_in_many_accounts")

    @pytest.mark.parametrize(
        "invalid_edit, expected_code",
        [
            ({"change_reason": "Regra inexistente", "rules": [{"code": "rule_that_does_not_exist", "points": 10}]}, "QIT001012"),
            ({"change_reason": "Mexe no limite noturno", "rules": [{"code": "nightly_limit_exceeded", "enabled": False}]}, "QIT001013"),
            ({"change_reason": "Janela onde não existe", "rules": [{"code": "same_owner", "window_minutes": 60}]}, "QIT001014"),
            ({"change_reason": "Limite onde não existe", "rules": [{"code": "new_account_above_cap", "threshold": 2}]}, "QIT001014"),
            ({"change_reason": "Limite de PJ onde não existe", "rules": [{"code": "known_destination", "company_threshold": 10}]}, "QIT001014"),
            ({"change_reason": "Pontos em eliminatória", "rules": [{"code": "device_used_by_many_sources", "points": 10}]}, "QIT001014"),
            ({"change_reason": "Meio pagador", "rules": [{"code": "burst_of_pix", "threshold": 2.5}]}, "QIT001014"),
            ({"change_reason": "Mais de duas casas", "rules": [{"code": "amount_above_baseline", "threshold": 4.005}]}, "QIT001014"),
            ({"change_reason": "Limite com três casas", "rules": [{"code": "amount_above_baseline", "threshold": 4.555}]}, "QIT001014"),
            ({"change_reason": "Limite que viraria zero", "rules": [{"code": "amount_above_baseline", "threshold": 0.001}]}, "QIT001014"),
            ({"change_reason": "Aparelho cadastrado há mais de 10 anos", "rules": [{"code": "long_registered_device", "threshold": 3651}]}, "QIT001014"),
            ({"change_reason": "Aparelho cadastrado há um milhão de dias", "rules": [{"code": "long_registered_device", "threshold": 1000000}]}, "QIT001014"),
            (
                {"change_reason": "Conta de destino recente por milênios", "rules": [{"code": "destination_account_opened_recently", "threshold": 9999999999}]},
                "QIT001014",
            ),
            (
                {"change_reason": "Limite de PJ com três casas", "rules": [{"code": "destination_document_in_many_accounts", "company_threshold": 10.005}]},
                "QIT001014",
            ),
            (
                {"change_reason": "Regra repetida", "rules": [{"code": "burst_of_pix", "points": 20}, {"code": "burst_of_pix", "points": 30}]},
                "QIT001015",
            ),
            ({"change_reason": "Reprova antes do 2FA", "parameters": {"rejection_score_threshold": 40}}, "QIT001016"),
            ({"change_reason": "Pontuação negativa", "rules": [{"code": "burst_of_pix", "points": -5}]}, "QIT001016"),
            ({"change_reason": "Redutor positivo", "rules": [{"code": "same_owner", "points": 10}]}, "QIT001016"),
            (
                {"change_reason": "Faixas de idade trocadas", "rules": [{"code": "destination_account_opened_very_recently", "threshold": 30}]},
                "QIT001016",
            ),
            ({"change_reason": "Mês maior que o histórico", "parameters": {"history_window_days": 30}}, "QIT001016"),
            ({"change_reason": "Relação acima da contraparte", "parameters": {"counterparty_relationship_cap": 80}}, "QIT001016"),
            ({"change_reason": "Faixas de valor trocadas", "rules": [{"code": "amount_far_above_baseline", "threshold": 5}]}, "QIT001016"),
        ],
    )
    def test_inconsistent_edit_is_refused_with_422_and_creates_no_version(self, invalid_edit, expected_code):
        version_before = current_bank_policy()["version"]

        status, body = RequestGenerator.POST_risk_policy_version(invalid_edit)

        assert_error(status, body, 422, expected_code)
        assert_policy_unchanged(version_before)

    @pytest.mark.parametrize(
        "invalid_body",
        [
            {},
            {"change_reason": "   "},
            {"change_reason": "Parâmetro desconhecido", "parameters": {"unknown_parameter": 1}},
            {"change_reason": "Modelo desconhecido", "based_on_template": "aggressive"},
            {"change_reason": "Ajuste vazio", "rules": [{"code": "burst_of_pix"}]},
            {"change_reason": "Tipo errado", "parameters": {"two_factor_score_threshold": "40"}},
            {"change_reason": "Aceite sem autor", "risk_acknowledged": True},
            {"change_reason": "Motivo com \u0000 no meio"},
            {"change_reason": "Motivo com meio caractere \ud800"},
            {"change_reason": "Autor com byte nulo", "requested_by": "analista\u0000"},
        ],
    )
    def test_invalid_body_is_refused_with_400_and_creates_no_version(self, invalid_body):
        version_before = current_bank_policy()["version"]

        status, body = RequestGenerator.POST_risk_policy_version(invalid_body)

        assert_error(status, body, 400, "QIT000001")
        assert_policy_unchanged(version_before)

    def test_edit_without_internal_token_is_refused_with_403(self):
        version_before = current_bank_policy()["version"]

        response = ClientRequisition.send("POST", "/risk-policy/versions", payload={"change_reason": "Sem token"})

        assert_error(response.response_status, response.response_json, 403, "QIT000002")
        assert_policy_unchanged(version_before)

    def test_parallel_edits_never_create_the_same_version_twice(self, restore_bank_policy):
        edits = [
            {"change_reason": f"Edição simultânea {position}", "parameters": {"destination_risk_alert_threshold": 30 - position}}
            for position in range(5)
        ]

        responses = send_all_at_the_same_time([lambda edit=edit: RequestGenerator.POST_risk_policy_version(edit) for edit in edits])

        created_versions = [body["version"] for status, body in responses if status == 201]
        refused = [body for status, body in responses if status != 201]
        assert created_versions
        assert len(created_versions) == len(set(created_versions))
        assert all(status in (201, 409) for status, _ in responses)
        assert all(body["code"] == "QIT001017" for body in refused)


def find_guardrail(guardrails, setting_name):
    for guardrail_row in guardrails["guardrails"]:
        if guardrail_row["setting"] == setting_name:
            return guardrail_row
    raise AssertionError(f"A faixa de segurança de {setting_name} não existe")


class TestRiskPolicyGuardrails:
    def test_guardrails_show_the_reference_the_limits_and_the_anchor_cases(self):
        status, body = RequestGenerator.GET_risk_policy_guardrails()

        assert status == 200
        assert body["reference"] == {"name": "balanced", "version": 1}
        assert find_guardrail(body, "rejection_score_threshold") == {"setting": "rejection_score_threshold", "loosens_when": "higher", "recommended": 70, "loosest_accepted_value": 80}
        assert find_guardrail(body, "new_destination_above_usual_ceiling.points") == {
            "setting": "new_destination_above_usual_ceiling.points",
            "loosens_when": "lower",
            "recommended": 30,
            "loosest_accepted_value": None,
        }
        assert {anchor_case["code"] for anchor_case in body["anchor_cases"]} == {
            "account_takeover_with_high_amount",
            "mule_flagged_by_the_base",
            "false_call_center",
        }

    def test_stricter_edit_needs_no_acknowledgment(self, restore_bank_policy):
        status, body = RequestGenerator.POST_risk_policy_version({"change_reason": "Reprova mais cedo", "parameters": {"rejection_score_threshold": 65}})

        assert status == 201
        assert body["risk_acknowledged"] is False
        assert body["requested_by"] is None

    def test_loosening_without_acknowledging_the_risk_is_refused_with_422_and_creates_no_version(self):
        version_before = current_bank_policy()["version"]

        status, body = RequestGenerator.POST_risk_policy_version({"change_reason": "Reprova mais tarde", "parameters": {"rejection_score_threshold": 75}})

        assert_error(status, body, 422, "QIT001020")
        assert "rejection_score_threshold" in body["description"]
        assert_policy_unchanged(version_before)

    def test_acknowledged_loosening_is_recorded_with_who_asked(self, restore_bank_policy):
        status, body = RequestGenerator.POST_risk_policy_version(
            {"change_reason": "Reprova mais tarde", "parameters": {"rejection_score_threshold": 75}, **RISK_ACKNOWLEDGEMENT}
        )

        assert status == 201
        assert body["risk_acknowledged"] is True
        assert body["requested_by"] == RISK_ACKNOWLEDGEMENT["requested_by"]
        assert current_bank_policy() == body

    def test_loosening_beyond_the_safety_limit_is_refused_even_when_acknowledged(self):
        version_before = current_bank_policy()["version"]

        status, body = RequestGenerator.POST_risk_policy_version(
            {"change_reason": "Reprova só no extremo", "parameters": {"rejection_score_threshold": 85}, **RISK_ACKNOWLEDGEMENT}
        )

        assert_error(status, body, 422, "QIT001018")
        assert_policy_unchanged(version_before)

    def test_eliminatory_rule_cannot_be_disabled_even_when_acknowledged(self):
        version_before = current_bank_policy()["version"]

        status, body = RequestGenerator.POST_risk_policy_version(
            {"change_reason": "Desliga o aparelho compartilhado", "rules": [{"code": "device_used_by_many_sources", "enabled": False}], **RISK_ACKNOWLEDGEMENT}
        )

        assert_error(status, body, 422, "QIT001018")
        assert_policy_unchanged(version_before)

    def test_edit_that_stops_catching_an_anchor_case_is_refused_even_when_acknowledged(self):
        version_before = current_bank_policy()["version"]

        status, body = RequestGenerator.POST_risk_policy_version(
            {"change_reason": "Destino novo sem peso", "rules": [{"code": "new_destination_above_usual_ceiling", "points": 0}], **RISK_ACKNOWLEDGEMENT}
        )

        assert_error(status, body, 422, "QIT001019")
        assert "Falsa central" in body["translation"]
        assert "Invasão de conta com valor alto" in body["translation"]
        assert_policy_unchanged(version_before)

    def test_switching_to_the_permissive_template_requires_acknowledging_the_risk(self, restore_bank_policy):
        refused_status, refused_body = RequestGenerator.POST_risk_policy_version({"change_reason": "Passa ao permissivo", "based_on_template": "permissive"})

        accepted_status, accepted_body = RequestGenerator.POST_risk_policy_version(
            {"change_reason": "Passa ao permissivo", "based_on_template": "permissive", **RISK_ACKNOWLEDGEMENT}
        )

        assert_error(refused_status, refused_body, 422, "QIT001020")
        assert accepted_status == 201
        assert accepted_body["based_on"] == {"name": "permissive", "version": 1}
