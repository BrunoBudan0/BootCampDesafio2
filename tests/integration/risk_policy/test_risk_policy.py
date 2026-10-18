from datetime import timedelta

import pytest

from tests.utils.assertions import assert_error, assert_rule_fired, assert_rule_not_fired, rule_hit
from tests.utils.clock import business_hours_today
from tests.utils.pix_payload import (
    new_company_payee,
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
    fire_together,
    payer_with_accepted_history,
    restore_balanced_bank_policy,
)


POLICY_FIELDS = {"name", "version", "change_reason", "based_on", "parameters", "rules"}
RULE_SETTING_FIELDS = {"code", "kind", "family", "enabled", "points", "threshold", "window_minutes", "company_threshold"}
PARAMETERS = {
    "history_window_days",
    "source_history_weight",
    "population_median_weight",
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
    "two_factor_score_threshold",
    "rejection_score_threshold",
    "two_factor_validity_minutes",
    "destination_alert_threshold",
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
    "source_history_weight": 5,
    "population_median_weight": 30,
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
    "counterparty_family_cap": 40,
    "two_factor_score_threshold": 40,
    "rejection_score_threshold": 70,
    "two_factor_validity_minutes": 10,
    "destination_alert_threshold": 30,
    "short_term_window_minutes": 1440,
}


@pytest.fixture
def restore_bank_policy():
    yield
    restore_balanced_bank_policy()


def rule_setting(policy, code):
    for setting in policy["rules"]:
        if setting["code"] == code:
            return setting
    raise AssertionError(f"A política não traz o ajuste da regra {code}")


def template(name):
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
        assert set(body["parameters"]) == PARAMETERS
        assert {setting["code"] for setting in body["rules"]} == EDITABLE_RULES
        assert all(set(setting) == RULE_SETTING_FIELDS for setting in body["rules"])

    def test_regulatory_rules_are_not_part_of_the_policy(self):
        policy = current_bank_policy()

        codes = {setting["code"] for setting in policy["rules"]}
        assert "nightly_limit_exceeded" not in codes
        assert "unregistered_device_limit_exceeded" not in codes

    def test_templates_differ_only_in_the_amount_multiplier(self):
        multipliers = {
            name: rule_setting(template(name), "amount_above_baseline")["threshold"]
            for name in ("conservative", "balanced", "permissive")
        }

        assert multipliers == {"conservative": 3, "balanced": 5, "permissive": 10}
        assert template("conservative")["parameters"] == template("permissive")["parameters"] == BALANCED_PARAMETERS

    def test_bank_policy_follows_the_balanced_template(self):
        policy = current_bank_policy()
        balanced = template("balanced")

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
        assert rule_setting(body, "burst_of_pix") == dict(rule_setting(before, "burst_of_pix"), points=30)
        assert current_bank_policy() == body

    def test_decimal_threshold_is_returned_as_saved(self, restore_bank_policy):
        created = edit_bank_policy(
            {"change_reason": "Multiplicador entre o equilibrado e o conservador", "rules": [{"code": "amount_above_baseline", "threshold": 4.5}]},
            "editar o multiplicador",
        )

        assert rule_setting(created, "amount_above_baseline")["threshold"] == 4.5
        assert rule_setting(current_bank_policy(), "amount_above_baseline")["threshold"] == 4.5

    def test_old_version_stays_readable_and_unchanged(self, restore_bank_policy):
        before = current_bank_policy()
        edit_bank_policy({"change_reason": "Muda a validade do 2FA", "parameters": {"two_factor_validity_minutes": 5}}, "editar a política")

        status, old_version = RequestGenerator.GET_risk_policy_version(before["version"])

        assert status == 200
        assert old_version == before

    def test_version_based_on_a_template_copies_the_template(self, restore_bank_policy):
        edit_bank_policy({"change_reason": "Ajusta antes de trocar de modelo", "parameters": {"two_factor_score_threshold": 35}}, "editar a política")

        status, body = RequestGenerator.POST_risk_policy_version({"change_reason": "Passa a seguir o modelo conservador", "based_on_template": "conservative"})

        assert status == 201
        assert body["based_on"] == {"name": "conservative", "version": 1}
        assert body["parameters"]["two_factor_score_threshold"] == 40
        assert rule_setting(body, "amount_above_baseline")["threshold"] == 3

    def test_new_analyses_record_the_new_version(self, restore_bank_policy):
        edited = edit_bank_policy({"change_reason": "Versão para conferir a análise", "parameters": {"destination_alert_threshold": 25}}, "editar a política")

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today()))

        assert analysis["metadata"]["policy"] == {"name": "bank", "version": edited["version"]}

    def test_disabled_rule_stops_firing(self, restore_bank_policy):
        transaction_date = business_hours_today()
        edit_bank_policy(
            {"change_reason": "Desliga a conta de destino muito recente", "rules": [{"code": "destination_account_opened_very_recently", "enabled": False}]},
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

        assert rule_hit(analysis, "destination_account_opened_very_recently")["points"] == 35

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
        edit_bank_policy({"change_reason": "Piso das regras de valor em R$ 10.000", "parameters": {"amount_rules_floor_cents": 1000000}}, "subir o piso")

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 200000))

        assert_rule_not_fired(analysis, "amount_above_baseline")

    def test_amount_floor_is_compared_with_the_accumulated_amount(self, restore_bank_policy):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)
        edit_bank_policy({"change_reason": "Piso das regras de valor em R$ 10.000", "parameters": {"amount_rules_floor_cents": 1000000}}, "subir o piso")
        payee = new_individual_payee()
        analyze(pix_payload(payer, payee, transaction_date, 600000))

        analysis = analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=1), 600000))

        assert_rule_fired(analysis, "amount_above_baseline")

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
            ({"change_reason": "Limite de PJ onde não existe", "rules": [{"code": "burst_of_pix", "company_threshold": 10}]}, "QIT001014"),
            ({"change_reason": "Pontos em eliminatória", "rules": [{"code": "device_used_by_many_sources", "points": 10}]}, "QIT001014"),
            ({"change_reason": "Meio pagador", "rules": [{"code": "burst_of_pix", "threshold": 2.5}]}, "QIT001014"),
            ({"change_reason": "Mais de duas casas", "rules": [{"code": "amount_above_baseline", "threshold": 4.005}]}, "QIT001014"),
            ({"change_reason": "Limite com três casas", "rules": [{"code": "amount_above_baseline", "threshold": 4.555}]}, "QIT001014"),
            ({"change_reason": "Limite que viraria zero", "rules": [{"code": "amount_above_baseline", "threshold": 0.001}]}, "QIT001014"),
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
            {"change_reason": f"Edição simultânea {position}", "parameters": {"destination_alert_threshold": 30 + position}}
            for position in range(5)
        ]

        responses = fire_together([lambda edit=edit: RequestGenerator.POST_risk_policy_version(edit) for edit in edits])

        created_versions = [body["version"] for status, body in responses if status == 201]
        refused = [body for status, body in responses if status != 201]
        assert created_versions
        assert len(created_versions) == len(set(created_versions))
        assert all(status in (201, 409) for status, _ in responses)
        assert all(body["code"] == "QIT001017" for body in refused)
