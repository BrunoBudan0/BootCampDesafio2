from datetime import timedelta

from tests.utils.assertions import assert_rule_fired, assert_rule_not_fired, rule_codes
from tests.utils.clock import business_hours_today
from tests.utils.pix_payload import (
    MANAUS_LOCATION,
    SAO_PAULO_LOCATION,
    new_individual_payee,
    new_individual_payer,
    payer_on_another_device,
    pix_payload,
)
from tests.utils.random_generator import RandomGenerator
from tests.utils.scenario import analyze, analyze_expecting, new_account_payer, payer_with_accepted_history


def payers_using_the_same_device(device_id, transaction_date, count):
    for position in range(count):
        analyze(
            pix_payload(new_individual_payer(), new_individual_payee(), transaction_date, device_id=device_id),
            f"usar o mesmo aparelho com outro pagador ({position + 1} de {count})",
        )


def payer_last_seen_in_sao_paulo(transaction_date):
    payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
    analyze_expecting(
        pix_payload(payer, payee, transaction_date, location=SAO_PAULO_LOCATION),
        "approved",
        "fazer um Pix em São Paulo",
    )
    return payer, payee


class TestDeviceUsedByManySources:
    def test_fifth_payer_on_the_same_device_within_24_hours_is_rejected(self):
        transaction_date = business_hours_today()
        device_id = RandomGenerator.generate_device_id()
        payers_using_the_same_device(device_id, transaction_date - timedelta(hours=23), 4)

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), transaction_date, device_id=device_id))

        assert analysis["status"] == "rejected"
        assert_rule_fired(analysis, "device_used_by_many_sources")

    def test_fourth_payer_on_the_same_device_is_not_rejected_by_it(self):
        transaction_date = business_hours_today()
        device_id = RandomGenerator.generate_device_id()
        payers_using_the_same_device(device_id, transaction_date - timedelta(hours=1), 3)

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), transaction_date, device_id=device_id))

        assert_rule_not_fired(analysis, "device_used_by_many_sources")

    def test_payers_from_24_hours_ago_or_more_do_not_count(self):
        transaction_date = business_hours_today()
        device_id = RandomGenerator.generate_device_id()
        payers_using_the_same_device(device_id, transaction_date - timedelta(hours=24), 4)

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), transaction_date, device_id=device_id))

        assert_rule_not_fired(analysis, "device_used_by_many_sources")

    def test_the_same_payer_repeating_the_device_counts_once(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer()
        for minute in range(4):
            analyze(pix_payload(payer, new_individual_payee(), transaction_date - timedelta(hours=2, minutes=minute)))

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date))

        assert_rule_not_fired(analysis, "device_used_by_many_sources")


class TestImpossibleTravelOnUnregisteredDevice:
    def test_travel_above_900_kmh_on_an_unregistered_device_is_rejected(self):
        transaction_date = business_hours_today()
        payer, payee = payer_last_seen_in_sao_paulo(transaction_date)

        analysis = analyze(
            pix_payload(payer_on_another_device(payer), payee, transaction_date + timedelta(hours=1), location=MANAUS_LOCATION)
        )

        assert analysis["status"] == "rejected"
        assert rule_codes(analysis) == {"impossible_travel_on_unregistered_device"}

    def test_travel_below_900_kmh_on_an_unregistered_device_is_not_impossible(self):
        transaction_date = business_hours_today()
        payer, payee = payer_last_seen_in_sao_paulo(transaction_date)

        analysis = analyze(
            pix_payload(payer_on_another_device(payer), payee, transaction_date + timedelta(hours=4), location=MANAUS_LOCATION)
        )

        assert_rule_not_fired(analysis, "impossible_travel_on_unregistered_device")
        assert_rule_not_fired(analysis, "impossible_travel")

    def test_travel_on_the_registered_device_is_not_eliminatory(self):
        transaction_date = business_hours_today()
        payer, payee = payer_last_seen_in_sao_paulo(transaction_date)

        analysis = analyze(pix_payload(payer, payee, transaction_date + timedelta(hours=1), location=MANAUS_LOCATION))

        assert_rule_not_fired(analysis, "impossible_travel_on_unregistered_device")
        assert_rule_fired(analysis, "impossible_travel")


class TestNewAccountToNewDestinationFarAboveCap:
    def test_new_account_paying_a_new_destination_above_five_times_the_cap_is_rejected(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_account_payer(transaction_date), new_individual_payee(), transaction_date, 500001))

        assert analysis["status"] == "rejected"
        assert rule_codes(analysis) == {"new_account_to_new_destination_far_above_cap"}

    def test_exactly_five_times_the_cap_is_not_rejected_by_it(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_account_payer(transaction_date), new_individual_payee(), transaction_date, 500000))

        assert_rule_not_fired(analysis, "new_account_to_new_destination_far_above_cap")

    def test_split_pix_to_the_same_new_destination_add_up(self):
        transaction_date = business_hours_today()
        payer = new_account_payer(transaction_date)
        payee = new_individual_payee()
        analyze_expecting(pix_payload(payer, payee, transaction_date, 300000), "two_factor_required", "primeira parte do valor")

        analysis = analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=2), 250000))

        assert_rule_fired(analysis, "new_account_to_new_destination_far_above_cap")

    def test_destination_already_in_the_history_is_not_new(self):
        transaction_date = business_hours_today()
        payer = new_account_payer(transaction_date)
        payee = new_individual_payee()
        analyze_expecting(pix_payload(payer, payee, transaction_date - timedelta(days=2)), "approved", "pagar o recebedor antes")

        analysis = analyze(pix_payload(payer, payee, transaction_date, 600000))

        assert_rule_not_fired(analysis, "new_account_to_new_destination_far_above_cap")

    def test_established_account_is_not_new(self):
        transaction_date = business_hours_today()

        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), transaction_date, 600000))

        assert_rule_not_fired(analysis, "new_account_to_new_destination_far_above_cap")
