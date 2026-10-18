from datetime import timedelta

from tests.utils.assertions import assert_rule_fired, assert_rule_not_fired, fired_rule_hit
from tests.utils.clock import business_hours_today
from tests.utils.pix_payload import new_individual_payee, new_individual_payer, pix_payload
from tests.utils.scenario import analyze, payer_with_accepted_history


class TestAmountAboveBaseline:
    def test_pix_above_five_times_the_baseline_adds_25_points(self):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 200000))

        assert fired_rule_hit(analysis, "amount_above_baseline")["points"] == 25

    def test_pix_above_twenty_times_the_baseline_adds_35_points_instead_of_25(self):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 5000000))

        assert fired_rule_hit(analysis, "amount_far_above_baseline")["points"] == 35
        assert_rule_not_fired(analysis, "amount_above_baseline")

    def test_reason_shows_the_multiplier_as_a_plain_number(self):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 200000))

        assert "acima de 5 vezes a base" in fired_rule_hit(analysis, "amount_above_baseline")["reason"]

    def test_pix_below_five_times_the_baseline_is_within_the_pattern(self):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date, 40000))

        assert_rule_not_fired(analysis, "amount_above_baseline")

    def test_payer_without_accepted_pix_is_not_judged_by_amount(self):
        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today(), 100000000))

        assert_rule_not_fired(analysis, "amount_above_baseline")

    def test_split_pix_to_the_same_destination_add_up_against_the_baseline(self):
        transaction_date = business_hours_today()
        payer, _, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)
        payee = new_individual_payee()

        first_part = analyze(pix_payload(payer, payee, transaction_date, 45000))
        analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=1), 45000))
        third_part = analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=2), 45000))

        assert_rule_not_fired(first_part, "amount_above_baseline")
        assert_rule_fired(third_part, "amount_above_baseline")


class TestMonthlyVolumeAboveTypical:
    def test_month_above_three_times_the_typical_month_adds_20_points(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(
            transaction_date - timedelta(days=50),
            2,
            spacing=timedelta(days=30),
        )

        analysis = analyze(pix_payload(payer, payee, transaction_date, 40000))

        assert fired_rule_hit(analysis, "monthly_volume_above_typical")["points"] == 20

    def test_month_within_three_times_the_typical_month_does_not_add_points(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(
            transaction_date - timedelta(days=50),
            2,
            spacing=timedelta(days=30),
        )

        analysis = analyze(pix_payload(payer, payee, transaction_date, 30000))

        assert_rule_not_fired(analysis, "monthly_volume_above_typical")

    def test_less_than_a_month_of_history_before_the_last_30_days_is_not_compared(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=45), 1)

        analysis = analyze(pix_payload(payer, payee, transaction_date, 500000))

        assert_rule_not_fired(analysis, "monthly_volume_above_typical")

    def test_payer_without_accepted_pix_is_not_judged_by_monthly_volume(self):
        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today(), 500000))

        assert_rule_not_fired(analysis, "monthly_volume_above_typical")
