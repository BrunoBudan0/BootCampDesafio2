from datetime import timedelta

from tests.utils.assertions import assert_rule_fired, assert_rule_not_fired, rule_hit
from tests.utils.clock import business_hours_today, today_at
from tests.utils.pix_payload import (
    new_company_payee,
    new_company_payer,
    new_individual_payee,
    new_individual_payer,
    pix_payload,
)
from tests.utils.scenario import analyze, analyze_expecting, confirm_two_factor, new_account_payer, two_factor_pix


class TestNewAccountAboveCap:
    def test_individual_new_account_above_1000_reais_adds_40_points(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_account_payer(transaction_date), new_company_payee(), transaction_date, 100001))

        assert rule_hit(analysis, "new_account_above_cap")["points"] == 40

    def test_individual_new_account_at_1000_reais_is_within_the_cap(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_account_payer(transaction_date), new_company_payee(), transaction_date, 100000))

        assert_rule_not_fired(analysis, "new_account_above_cap")

    def test_account_with_29_days_is_still_new(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer(opening_date=transaction_date - timedelta(days=29))

        analysis = analyze(pix_payload(payer, new_company_payee(), transaction_date, 150000))

        assert_rule_fired(analysis, "new_account_above_cap")

    def test_account_with_30_days_is_no_longer_new(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer(opening_date=transaction_date - timedelta(days=30))

        analysis = analyze(pix_payload(payer, new_company_payee(), transaction_date, 150000))

        assert_rule_not_fired(analysis, "new_account_above_cap")

    def test_company_new_account_cap_is_10000_reais(self):
        transaction_date = business_hours_today()
        opening_date = transaction_date - timedelta(days=10)

        within_cap = analyze(pix_payload(new_company_payer(opening_date), new_company_payee(), transaction_date, 1000000))
        above_cap = analyze(pix_payload(new_company_payer(opening_date), new_company_payee(), transaction_date, 1000001))

        assert_rule_not_fired(within_cap, "new_account_above_cap")
        assert_rule_fired(above_cap, "new_account_above_cap")

    def test_split_pix_of_a_new_account_add_up_against_the_cap(self):
        transaction_date = business_hours_today()
        payer = new_account_payer(transaction_date)
        analyze(pix_payload(payer, new_company_payee(), transaction_date, 60000), "primeira parte do valor")

        analysis = analyze(pix_payload(payer, new_company_payee(), transaction_date + timedelta(minutes=10), 50000))

        assert_rule_fired(analysis, "new_account_above_cap")

    def test_pending_two_factor_uses_the_cap(self):
        transaction_date = business_hours_today()
        payer, _, _, _ = two_factor_pix(transaction_date)

        analysis = analyze(pix_payload(payer, new_company_payee(), transaction_date + timedelta(minutes=1)))

        assert_rule_fired(analysis, "new_account_above_cap")

    def test_denied_two_factor_does_not_use_the_cap(self):
        transaction_date = business_hours_today()
        payer, _, payload, _ = two_factor_pix(transaction_date)
        confirm_two_factor(payload["id"], "denied", transaction_date + timedelta(seconds=30))

        analysis = analyze(pix_payload(payer, new_company_payee(), transaction_date + timedelta(minutes=1)))

        assert_rule_not_fired(analysis, "new_account_above_cap")

    def test_expired_two_factor_does_not_use_the_cap(self):
        transaction_date = business_hours_today()
        payer, _, _, _ = two_factor_pix(transaction_date)

        analysis = analyze(pix_payload(payer, new_company_payee(), transaction_date + timedelta(minutes=11)))

        assert_rule_not_fired(analysis, "new_account_above_cap")


class TestBurstOfPix:
    def test_fifth_pix_within_five_minutes_adds_25_points(self):
        first_moment = business_hours_today()
        payer = new_individual_payer()
        for minute in range(4):
            analyze(pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=minute)))

        analysis = analyze(pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=4, seconds=59)))

        assert rule_hit(analysis, "burst_of_pix")["points"] == 25

    def test_pix_from_five_minutes_ago_or_more_do_not_count(self):
        first_moment = business_hours_today()
        payer = new_individual_payer()
        for minute in range(4):
            analyze(pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=minute)))

        analysis = analyze(pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=5)))

        assert_rule_not_fired(analysis, "burst_of_pix")

    def test_rejected_attempts_also_count(self):
        first_moment = today_at(23)
        payer = new_individual_payer()
        for minute in range(4):
            analyze_expecting(
                pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=minute), 150000),
                "rejected",
                f"tentativa reprovada pelo limite noturno ({minute + 1} de 4)",
            )

        analysis = analyze(pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=4)))

        assert_rule_fired(analysis, "burst_of_pix")
