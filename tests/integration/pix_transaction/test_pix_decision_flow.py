from dataclasses import replace
from datetime import timedelta

from tests.utils.assertions import rule_codes, rule_hit
from tests.utils.clock import business_hours_today, now_in_sao_paulo, parse_iso, today_at
from tests.utils.pix_payload import (
    new_company_payee,
    new_individual_payee,
    new_individual_payer,
    payee_owned_by,
    payer_on_another_device,
    pix_payload,
    same_payee_in_another_account,
)
from tests.utils.request_generator import RequestGenerator
from tests.utils.scenario import (
    analyze,
    current_bank_policy,
    fire_together,
    new_account_payer,
    payer_with_accepted_history,
)


RULE_HIT_FIELDS = {"code", "kind", "family", "points", "reason"}


def very_recent_individual_payee(transaction_date):
    return new_individual_payee(opening_date=transaction_date - timedelta(days=3))


def other_payers_paying(payee, transaction_date, count):
    for position in range(count):
        analyze(
            pix_payload(new_individual_payer(), payee, transaction_date - timedelta(minutes=10 + position)),
            f"pagar o mesmo recebedor com outro pagador ({position + 1} de {count})",
        )


class TestPixDecisionFlow:
    def test_pix_without_any_signal_is_approved_with_zero_score_and_no_rules(self):
        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today()))

        assert analysis["status"] == "approved"
        assert analysis["metadata"]["risk_score"] == 0
        assert analysis["metadata"]["destination_risk"] == 0
        assert analysis["metadata"]["rules"] == []
        assert analysis["metadata"]["alerts"] == []
        assert analysis["metadata"]["two_factor"] is None

    def test_family_points_stop_at_the_family_cap(self):
        transaction_date = business_hours_today()
        payee = very_recent_individual_payee(transaction_date)
        other_payers_paying(payee, transaction_date, 4)

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert {"destination_account_opened_very_recently", "destination_receiving_from_many_sources"} <= rule_codes(analysis)
        assert analysis["metadata"]["risk_score"] == 40
        assert analysis["status"] == "two_factor_required"

    def test_destination_risk_adds_counterparty_points_without_the_cap(self):
        transaction_date = business_hours_today()
        payee = very_recent_individual_payee(transaction_date)
        other_payers_paying(payee, transaction_date, 4)

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert analysis["metadata"]["destination_risk"] == 55

    def test_reducers_subtract_from_the_score(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer()

        analysis = analyze(pix_payload(payer, payee_owned_by(payer, opening_date=transaction_date - timedelta(days=3)), transaction_date))

        assert {"destination_account_opened_very_recently", "same_owner"} <= rule_codes(analysis)
        assert analysis["metadata"]["risk_score"] == 0
        assert analysis["metadata"]["destination_risk"] == 0
        assert analysis["status"] == "approved"

    def test_score_never_goes_below_zero(self):
        payer = new_individual_payer()

        analysis = analyze(pix_payload(payer, payee_owned_by(payer), business_hours_today()))

        assert rule_hit(analysis, "same_owner")["points"] == -30
        assert analysis["metadata"]["risk_score"] == 0

    def test_score_from_seventy_is_rejected(self):
        transaction_date = business_hours_today()
        payee = very_recent_individual_payee(transaction_date)

        analysis = analyze(pix_payload(new_account_payer(transaction_date), payee, transaction_date, 150000))

        assert {"new_account_above_cap", "destination_account_opened_very_recently"} <= rule_codes(analysis)
        assert analysis["metadata"]["risk_score"] >= 70
        assert analysis["status"] == "rejected"

    def test_score_from_forty_to_sixty_nine_asks_two_factor(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_account_payer(transaction_date), new_company_payee(), transaction_date, 150000))

        assert 40 <= analysis["metadata"]["risk_score"] <= 69
        assert analysis["status"] == "two_factor_required"

    def test_regulatory_two_factor_wins_over_a_low_score(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)

        analysis = analyze(pix_payload(payer_on_another_device(payer), payee, transaction_date, 30000))

        assert rule_hit(analysis, "unregistered_device_limit_exceeded")["points"] == 0
        assert analysis["metadata"]["risk_score"] < 40
        assert analysis["status"] == "two_factor_required"

    def test_nightly_limit_rejection_wins_over_a_low_score_and_keeps_the_score(self):
        night = today_at(23)

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), night, 150000))

        assert "nightly_limit_exceeded" in rule_codes(analysis)
        assert analysis["metadata"]["risk_score"] is not None
        assert analysis["metadata"]["risk_score"] < 70
        assert analysis["status"] == "rejected"

    def test_eliminatory_rule_ends_the_analysis_without_score_and_without_other_rules(self):
        transaction_date = business_hours_today()
        shared_device = new_individual_payer().device_id
        payee = very_recent_individual_payee(transaction_date)
        for position in range(4):
            analyze(
                pix_payload(new_individual_payer(), new_individual_payee(), transaction_date - timedelta(minutes=10 + position), device_id=shared_device),
                f"usar o mesmo aparelho com outro pagador ({position + 1} de 4)",
            )

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date, device_id=shared_device))

        assert analysis["status"] == "rejected"
        assert rule_codes(analysis) == {"device_used_by_many_sources"}
        assert analysis["metadata"]["risk_score"] is None
        assert analysis["metadata"]["destination_risk"] is None

    def test_two_factor_expires_ten_minutes_after_the_transaction_date(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_account_payer(transaction_date), new_company_payee(), transaction_date, 150000))

        assert analysis["status"] == "two_factor_required"
        assert parse_iso(analysis["metadata"]["two_factor"]["expires_at"]) == transaction_date + timedelta(minutes=10)

    def test_analysis_records_the_bank_policy_version_in_force(self):
        policy = current_bank_policy()

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today()))

        assert analysis["metadata"]["policy"] == {"name": "bank", "version": policy["version"]}

    def test_each_rule_hit_carries_code_kind_family_points_and_reason(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_individual_payer(), very_recent_individual_payee(transaction_date), transaction_date))

        hit = rule_hit(analysis, "destination_account_opened_very_recently")
        assert set(hit) == RULE_HIT_FIELDS
        assert hit["kind"] == "scoring"
        assert hit["family"] == "counterparty"
        assert hit["points"] == 25
        assert hit["reason"].strip()

    def test_destination_risk_from_thirty_raises_an_alert_without_changing_the_decision(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        other_payers_paying(payee, transaction_date, 4)

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert analysis["status"] == "approved"
        assert analysis["metadata"]["alerts"] == [{"code": "destination_alert", "destination_risk": 30, "threshold": 30}]

    def test_very_recent_destination_account_alone_raises_no_alert(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_individual_payer(), very_recent_individual_payee(transaction_date), transaction_date))

        assert analysis["metadata"]["destination_risk"] == 25
        assert analysis["metadata"]["alerts"] == []

    def test_reducers_do_not_abate_signals_seen_by_the_whole_base(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer()
        own_account = payee_owned_by(payer)
        other_payers_paying(own_account, transaction_date, 4)

        analysis = analyze(pix_payload(payer, own_account, transaction_date))

        assert {"destination_receiving_from_many_sources", "same_owner"} <= rule_codes(analysis)
        assert analysis["metadata"]["risk_score"] == 0
        assert analysis["metadata"]["destination_risk"] == 30

    def test_known_destination_abates_the_relationship_signals(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)
        new_account_of_the_payee = replace(same_payee_in_another_account(payee), opening_date=transaction_date - timedelta(days=6))

        analysis = analyze(pix_payload(payer, new_account_of_the_payee, transaction_date))

        assert {"destination_account_opened_very_recently", "known_destination"} <= rule_codes(analysis)
        assert analysis["metadata"]["destination_risk"] == 5

    def test_eliminatory_rule_hides_a_regulatory_rule_that_would_also_fire(self):
        night = today_at(23)

        analysis = analyze(pix_payload(new_account_payer(night), new_individual_payee(), night, 500001))

        assert analysis["status"] == "rejected"
        assert rule_codes(analysis) == {"new_account_to_new_destination_far_above_cap"}

    def test_destination_risk_below_thirty_raises_no_alert(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee(opening_date=transaction_date - timedelta(days=20))

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert analysis["metadata"]["destination_risk"] == 20
        assert analysis["metadata"]["alerts"] == []

    def test_parallel_pix_of_the_same_payer_see_each_other(self):
        transaction_date = now_in_sao_paulo()
        payer = new_individual_payer()
        payloads = [pix_payload(payer, new_company_payee(), transaction_date) for _ in range(5)]

        responses = fire_together([lambda payload=payload: RequestGenerator.POST_pix_transaction(payload) for payload in payloads])

        assert [status for status, _ in responses] == [201] * 5
        burst_hits = [body for status, body in responses if "burst_of_pix" in rule_codes(body)]
        assert len(burst_hits) == 1

    def test_parallel_payers_on_the_same_device_see_each_other(self):
        transaction_date = now_in_sao_paulo()
        shared_device = new_individual_payer().device_id
        payloads = [pix_payload(new_individual_payer(), new_individual_payee(), transaction_date, device_id=shared_device) for _ in range(5)]

        responses = fire_together([lambda payload=payload: RequestGenerator.POST_pix_transaction(payload) for payload in payloads])

        assert [status for status, _ in responses] == [201] * 5
        rejected_by_shared_device = [body for _, body in responses if "device_used_by_many_sources" in rule_codes(body)]
        assert len(rejected_by_shared_device) == 1
        assert rejected_by_shared_device[0]["status"] == "rejected"

    def test_parallel_payers_of_the_same_destination_see_each_other(self):
        transaction_date = now_in_sao_paulo()
        payee = new_individual_payee()
        payloads = [pix_payload(new_individual_payer(), payee, transaction_date) for _ in range(5)]

        responses = fire_together([lambda payload=payload: RequestGenerator.POST_pix_transaction(payload) for payload in payloads])

        assert [status for status, _ in responses] == [201] * 5
        fan_in_hits = [body for _, body in responses if "destination_receiving_from_many_sources" in rule_codes(body)]
        assert len(fan_in_hits) == 1
