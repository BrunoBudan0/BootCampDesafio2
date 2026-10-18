from datetime import timedelta

from tests.utils.assertions import assert_rule_fired, assert_rule_not_fired, fired_rule_codes, fired_rule_hit
from tests.utils.clock import business_hours_today, today_at
from tests.utils.pix_payload import (
    new_company_payee,
    new_individual_payee,
    new_individual_payer,
    payee_owned_by,
    pix_payload,
    same_payee_in_another_account,
)
from tests.utils.scenario import (
    analyze,
    analyze_expecting,
    answer_two_factor,
    new_account_payer,
    pix_rejected_with_counterparty_signal,
    pix_rejected_by_nightly_limit,
    payer_with_accepted_history,
    new_account_pix_waiting_two_factor,
)


def payee_opened_days_ago(transaction_date, days):
    return new_individual_payee(opening_date=transaction_date - timedelta(days=days))


def other_payers_paying(payee, transaction_date, count):
    for position in range(count):
        analyze(
            pix_payload(new_individual_payer(), payee, transaction_date - timedelta(minutes=10 + position)),
            f"pagar o mesmo recebedor com outro pagador ({position + 1} de {count})",
        )


def payments_in_different_accounts(payee, transaction_date, count):
    accounts = [payee] + [same_payee_in_another_account(payee) for _ in range(count - 1)]
    for position, account in enumerate(accounts):
        analyze(
            pix_payload(new_individual_payer(), account, transaction_date - timedelta(minutes=30 + position)),
            f"pagar o mesmo documento em outra conta ({position + 1} de {count})",
        )
    return accounts


class TestDestinationAccountAge:
    def test_account_opened_six_days_ago_adds_25_points(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_individual_payer(), payee_opened_days_ago(transaction_date, 6), transaction_date))

        assert fired_rule_hit(analysis, "destination_account_opened_very_recently")["points"] == 25
        assert_rule_not_fired(analysis, "destination_account_opened_recently")

    def test_account_opened_seven_days_ago_adds_20_points(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_individual_payer(), payee_opened_days_ago(transaction_date, 7), transaction_date))

        assert fired_rule_hit(analysis, "destination_account_opened_recently")["points"] == 20
        assert_rule_not_fired(analysis, "destination_account_opened_very_recently")

    def test_account_opened_29_days_ago_is_still_recent(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_individual_payer(), payee_opened_days_ago(transaction_date, 29), transaction_date))

        assert_rule_fired(analysis, "destination_account_opened_recently")

    def test_account_opened_30_days_ago_is_not_recent(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_individual_payer(), payee_opened_days_ago(transaction_date, 30), transaction_date))

        assert_rule_not_fired(analysis, "destination_account_opened_recently")
        assert_rule_not_fired(analysis, "destination_account_opened_very_recently")


class TestNewDestinationAboveUsualCeiling:
    def history_with_ceiling_of_300_reais(self, transaction_date):
        payer = new_individual_payer()
        payee = new_individual_payee()
        for days_ago, amount_cents in ((4, 10000), (3, 30000), (2, 10000)):
            analyze_expecting(
                pix_payload(payer, payee, transaction_date - timedelta(days=days_ago), amount_cents),
                "approved",
                "montar um histórico com maior Pix de R$ 300",
            )
        return payer, payee

    def test_new_destination_above_the_largest_accepted_pix_adds_30_points(self):
        transaction_date = business_hours_today()
        payer, _ = self.history_with_ceiling_of_300_reais(transaction_date)

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 30001))

        assert fired_rule_hit(analysis, "new_destination_above_usual_ceiling")["points"] == 30

    def test_new_company_destination_within_three_times_the_ceiling_is_not_suspicious(self):
        transaction_date = business_hours_today()
        payer, _ = self.history_with_ceiling_of_300_reais(transaction_date)

        analysis = analyze(pix_payload(payer, new_company_payee(), transaction_date, 90000))

        assert_rule_not_fired(analysis, "new_destination_above_usual_ceiling")

    def test_new_company_destination_above_three_times_the_ceiling_adds_points(self):
        transaction_date = business_hours_today()
        payer, _ = self.history_with_ceiling_of_300_reais(transaction_date)

        analysis = analyze(pix_payload(payer, new_company_payee(), transaction_date, 90001))

        assert_rule_fired(analysis, "new_destination_above_usual_ceiling")

    def test_new_destination_at_the_largest_accepted_pix_is_within_the_ceiling(self):
        transaction_date = business_hours_today()
        payer, _ = self.history_with_ceiling_of_300_reais(transaction_date)

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 30000))

        assert_rule_not_fired(analysis, "new_destination_above_usual_ceiling")

    def test_destination_already_in_the_history_is_not_new(self):
        transaction_date = business_hours_today()
        payer, known_payee = self.history_with_ceiling_of_300_reais(transaction_date)

        analysis = analyze(pix_payload(payer, known_payee, transaction_date, 500000))

        assert_rule_not_fired(analysis, "new_destination_above_usual_ceiling")

    def test_split_pix_to_the_same_new_destination_add_up_against_the_ceiling(self):
        transaction_date = business_hours_today()
        payer, _ = self.history_with_ceiling_of_300_reais(transaction_date)
        payee = new_individual_payee()

        first_part = analyze(pix_payload(payer, payee, transaction_date, 20000))
        second_part = analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=1), 20000))

        assert_rule_not_fired(first_part, "new_destination_above_usual_ceiling")
        assert_rule_fired(second_part, "new_destination_above_usual_ceiling")

    def test_small_accepted_pix_do_not_lower_the_ceiling_below_the_baseline(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer()
        analyze_expecting(pix_payload(payer, new_company_payee(), transaction_date - timedelta(days=2), 1000), "approved", "pagar R$ 10 numa loja")

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 10000))

        assert_rule_not_fired(analysis, "new_destination_above_usual_ceiling")

    def test_pix_to_own_account_do_not_raise_the_usual_ceiling(self):
        transaction_date = business_hours_today()
        payer, _ = self.history_with_ceiling_of_300_reais(transaction_date)
        analyze_expecting(
            pix_payload(payer, payee_owned_by(payer), transaction_date - timedelta(days=1, hours=1), 3000000),
            "approved",
            "mover R$ 30.000 para conta própria",
        )

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 2000000))

        assert_rule_fired(analysis, "new_destination_above_usual_ceiling")

    def test_pix_accepted_in_the_last_24_hours_do_not_raise_the_usual_ceiling(self):
        transaction_date = business_hours_today()
        payer, _ = self.history_with_ceiling_of_300_reais(transaction_date)
        large_pix = pix_payload(payer, new_individual_payee(), transaction_date - timedelta(hours=1), 500000)
        analyze_expecting(large_pix, "two_factor_required", "Pix grande para destino novo")
        answer_two_factor(large_pix["id"], "confirmed", transaction_date - timedelta(minutes=59))

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 400000))

        assert_rule_fired(analysis, "new_destination_above_usual_ceiling")

    def test_payer_without_accepted_pix_is_compared_with_the_population_baseline(self):
        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today(), 100000000))

        assert_rule_fired(analysis, "new_destination_above_usual_ceiling")


class TestDestinationReceivingFromManySources:
    def test_fifth_payer_of_an_individual_within_one_hour_adds_30_points(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        other_payers_paying(payee, transaction_date, 4)

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert fired_rule_hit(analysis, "destination_receiving_from_many_sources")["points"] == 30

    def test_fourth_payer_of_an_individual_is_not_fan_in(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        other_payers_paying(payee, transaction_date, 3)

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert_rule_not_fired(analysis, "destination_receiving_from_many_sources")

    def test_payers_below_the_amount_rules_floor_do_not_count(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        for position in range(4):
            analyze(pix_payload(new_individual_payer(), payee, transaction_date - timedelta(minutes=10 + position), 9999))

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert_rule_not_fired(analysis, "destination_receiving_from_many_sources")

    def test_payers_from_one_hour_ago_or_more_do_not_count(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        for position in range(4):
            analyze(pix_payload(new_individual_payer(), payee, transaction_date - timedelta(hours=1, minutes=position)))

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert_rule_not_fired(analysis, "destination_receiving_from_many_sources")

    def test_company_receiving_from_many_payers_is_not_fan_in(self):
        transaction_date = business_hours_today()
        payee = new_company_payee()
        other_payers_paying(payee, transaction_date, 4)

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert_rule_not_fired(analysis, "destination_receiving_from_many_sources")


class TestDestinationRejectedForOtherSources:
    def test_destination_rejected_for_two_other_payers_adds_20_points(self):
        payee = new_individual_payee()
        rejected_at = business_hours_today() - timedelta(days=1)
        pix_rejected_with_counterparty_signal(payee, rejected_at)
        pix_rejected_with_counterparty_signal(payee, rejected_at + timedelta(minutes=5))

        analysis = analyze(pix_payload(new_individual_payer(), payee, business_hours_today()))

        assert fired_rule_hit(analysis, "destination_rejected_for_other_sources")["points"] == 20

    def test_destination_rejected_for_one_other_payer_does_not_add_points(self):
        payee = new_individual_payee()
        pix_rejected_with_counterparty_signal(payee, business_hours_today() - timedelta(days=1))

        analysis = analyze(pix_payload(new_individual_payer(), payee, business_hours_today()))

        assert_rule_not_fired(analysis, "destination_rejected_for_other_sources")

    def test_rejections_of_the_payer_itself_do_not_count(self):
        payee = new_individual_payee()
        rejected_at = business_hours_today() - timedelta(days=1)
        payer = new_account_payer(rejected_at)
        pix_rejected_with_counterparty_signal(payee, rejected_at, payer=payer)
        pix_rejected_with_counterparty_signal(payee, rejected_at + timedelta(minutes=5), payer=payer)

        analysis = analyze(pix_payload(payer, payee, business_hours_today()))

        assert_rule_not_fired(analysis, "destination_rejected_for_other_sources")

    def test_rejections_without_any_counterparty_signal_do_not_count(self):
        payee = new_individual_payee()
        night_transaction_date = today_at(23) - timedelta(days=1)
        for minutes_later in (0, 5):
            payer, history_payee, _ = payer_with_accepted_history(business_hours_today() - timedelta(days=4), 1)
            analyze_expecting(
                pix_payload(payer, history_payee, business_hours_today() - timedelta(days=3), 200000),
                "approved",
                "subir o teto habitual do pagador para R$ 2.000",
            )
            rejected = pix_rejected_by_nightly_limit(payee, night_transaction_date + timedelta(minutes=minutes_later), payer=payer)
            assert all(fired_rule["family"] != "counterparty" for fired_rule in rejected["metadata"]["rules"]), (
                "A preparação do cenário falhou: a reprovação pelo limite noturno não devia ter sinal de contraparte"
            )

        analysis = analyze(pix_payload(new_individual_payer(), payee, business_hours_today()))

        assert_rule_not_fired(analysis, "destination_rejected_for_other_sources")

    def test_denied_two_factor_of_other_payers_counts_as_rejection(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        for minutes_ago in (40, 20):
            started_at = transaction_date - timedelta(minutes=minutes_ago)
            _, _, payload, _ = new_account_pix_waiting_two_factor(started_at, payee=payee)
            answer_two_factor(payload["id"], "denied", started_at + timedelta(minutes=1))

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert_rule_fired(analysis, "destination_rejected_for_other_sources")

    def test_rejections_older_than_seven_days_do_not_count(self):
        payee = new_individual_payee()
        rejected_at = business_hours_today() - timedelta(days=8)
        pix_rejected_with_counterparty_signal(payee, rejected_at)
        pix_rejected_with_counterparty_signal(payee, rejected_at + timedelta(minutes=5))

        analysis = analyze(pix_payload(new_individual_payer(), payee, business_hours_today()))

        assert_rule_not_fired(analysis, "destination_rejected_for_other_sources")

    def test_rejections_in_which_this_rule_fired_do_not_feed_it(self):
        payee = new_individual_payee()
        first_rejections = business_hours_today() - timedelta(days=9)
        pix_rejected_with_counterparty_signal(payee, first_rejections)
        pix_rejected_with_counterparty_signal(payee, first_rejections + timedelta(minutes=5))
        second_night = today_at(23) - timedelta(days=8)
        for minutes_later in (0, 5):
            fed_by_the_rule = pix_rejected_by_nightly_limit(payee, second_night + timedelta(minutes=minutes_later))
            assert "destination_rejected_for_other_sources" in fired_rule_codes(fed_by_the_rule), (
                "A preparação do cenário falhou: a reprovação da segunda noite devia ter a regra disparada"
            )

        analysis = analyze(pix_payload(new_individual_payer(), payee, business_hours_today() - timedelta(days=1)))

        assert_rule_not_fired(analysis, "destination_rejected_for_other_sources")


class TestDestinationDocumentInManyAccounts:
    def test_individual_receiving_in_a_third_account_within_24_hours_adds_30_points(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        payments_in_different_accounts(payee, transaction_date, 2)

        analysis = analyze(pix_payload(new_individual_payer(), same_payee_in_another_account(payee), transaction_date))

        assert fired_rule_hit(analysis, "destination_document_in_many_accounts")["points"] == 30

    def test_the_same_account_paid_many_times_is_one_account(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        other_payers_paying(payee, transaction_date, 3)

        analysis = analyze(pix_payload(new_individual_payer(), payee, transaction_date))

        assert_rule_not_fired(analysis, "destination_document_in_many_accounts")

    def test_company_in_a_third_account_is_within_its_own_limit(self):
        transaction_date = business_hours_today()
        payee = new_company_payee()
        payments_in_different_accounts(payee, transaction_date, 2)

        analysis = analyze(pix_payload(new_individual_payer(), same_payee_in_another_account(payee), transaction_date))

        assert_rule_not_fired(analysis, "destination_document_in_many_accounts")

    def test_company_receiving_in_a_tenth_account_adds_30_points(self):
        transaction_date = business_hours_today()
        payee = new_company_payee()
        payments_in_different_accounts(payee, transaction_date, 9)

        analysis = analyze(pix_payload(new_individual_payer(), same_payee_in_another_account(payee), transaction_date))

        assert fired_rule_hit(analysis, "destination_document_in_many_accounts")["points"] == 30

    def test_accounts_used_24_hours_ago_or_more_do_not_count(self):
        transaction_date = business_hours_today()
        payee = new_individual_payee()
        payments_in_different_accounts(payee, transaction_date - timedelta(hours=24) + timedelta(minutes=29), 2)

        analysis = analyze(pix_payload(new_individual_payer(), same_payee_in_another_account(payee), transaction_date))

        assert_rule_not_fired(analysis, "destination_document_in_many_accounts")
