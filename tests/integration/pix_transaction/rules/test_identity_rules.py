from datetime import timedelta

from tests.utils.assertions import assert_rule_not_fired, rule_hit
from tests.utils.clock import business_hours_today
from tests.utils.pix_payload import (
    CAMPINAS_LOCATION,
    MANAUS_LOCATION,
    RIO_DE_JANEIRO_LOCATION,
    SAO_PAULO_LOCATION,
    SAO_PAULO_NEARBY_LOCATION,
    new_individual_payee,
    new_individual_payer,
    payer_on_another_device,
    pix_payload,
)
from tests.utils.random_generator import RandomGenerator
from tests.utils.scenario import (
    analyze,
    analyze_expecting,
    confirm_two_factor,
    payer_with_accepted_history,
    two_factor_pix,
)


class TestImpossibleTravel:
    def test_travel_above_900_kmh_on_a_registered_device_adds_40_points(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
        analyze_expecting(pix_payload(payer, payee, transaction_date, location=SAO_PAULO_LOCATION), "approved", "Pix em São Paulo")

        analysis = analyze(pix_payload(payer, payee, transaction_date + timedelta(hours=1), location=MANAUS_LOCATION))

        assert rule_hit(analysis, "impossible_travel")["points"] == 40

    def test_short_trip_above_50_km_in_a_few_minutes_is_still_impossible(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
        analyze_expecting(pix_payload(payer, payee, transaction_date, location=SAO_PAULO_LOCATION), "approved", "Pix em São Paulo")

        analysis = analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=3), location=CAMPINAS_LOCATION))

        assert rule_hit(analysis, "impossible_travel")["points"] == 40

    def test_location_change_below_50_km_is_not_travel_even_in_the_same_second(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
        analyze_expecting(pix_payload(payer, payee, transaction_date, location=SAO_PAULO_LOCATION), "approved", "Pix em São Paulo")

        analysis = analyze(pix_payload(payer, payee, transaction_date, location=SAO_PAULO_NEARBY_LOCATION))

        assert_rule_not_fired(analysis, "impossible_travel")

    def test_travel_is_measured_from_the_last_accepted_pix_and_not_from_a_rejected_attempt(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
        analyze_expecting(pix_payload(payer, payee, transaction_date, location=SAO_PAULO_LOCATION), "approved", "Pix do dono em São Paulo")
        analyze_expecting(
            pix_payload(payer_on_another_device(payer), new_individual_payee(), transaction_date + timedelta(minutes=10), location=MANAUS_LOCATION),
            "rejected",
            "tentativa de outro aparelho em Manaus",
        )

        analysis = analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=20), location=SAO_PAULO_LOCATION))

        assert_rule_not_fired(analysis, "impossible_travel")

    def test_travel_is_not_checked_without_geolocation_in_both_pix(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
        analyze_expecting(pix_payload(payer, payee, transaction_date), "approved", "Pix sem geolocalização")

        analysis = analyze(pix_payload(payer, payee, transaction_date + timedelta(minutes=5), location=MANAUS_LOCATION))

        assert_rule_not_fired(analysis, "impossible_travel")


class TestIpUnfamiliar:
    def test_ip_never_used_in_accepted_pix_adds_points_weighted_by_the_history(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, payee, transaction_date, ip=RandomGenerator.generate_ip()))

        assert rule_hit(analysis, "ip_unfamiliar")["points"] == 3

    def test_new_ip_weighs_more_for_a_payer_with_more_history(self):
        transaction_date = business_hours_today()
        short_history_payer, short_history_payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
        long_history_payer, long_history_payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 20)

        short_history = analyze(pix_payload(short_history_payer, short_history_payee, transaction_date, ip=RandomGenerator.generate_ip()))
        long_history = analyze(pix_payload(long_history_payer, long_history_payee, transaction_date, ip=RandomGenerator.generate_ip()))

        assert rule_hit(short_history, "ip_unfamiliar")["points"] == 1
        assert rule_hit(long_history, "ip_unfamiliar")["points"] == 8

    def test_ip_already_used_in_accepted_pix_adds_nothing(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, payee, transaction_date))

        assert_rule_not_fired(analysis, "ip_unfamiliar")

    def test_payer_without_accepted_pix_is_not_judged_by_ip(self):
        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today()))

        assert_rule_not_fired(analysis, "ip_unfamiliar")


class TestLocationUnfamiliar:
    def test_location_never_used_in_accepted_pix_adds_points_weighted_by_the_history(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3, location=SAO_PAULO_LOCATION)

        analysis = analyze(pix_payload(payer, payee, transaction_date, location=RIO_DE_JANEIRO_LOCATION))

        assert rule_hit(analysis, "location_unfamiliar")["points"] == 3

    def test_location_is_compared_rounded_to_two_decimal_places(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3, location=SAO_PAULO_LOCATION)

        analysis = analyze(pix_payload(payer, payee, transaction_date, location=SAO_PAULO_NEARBY_LOCATION))

        assert_rule_not_fired(analysis, "location_unfamiliar")

    def test_pix_without_geolocation_is_not_judged_by_location(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3, location=SAO_PAULO_LOCATION)

        analysis = analyze(pix_payload(payer, payee, transaction_date))

        assert_rule_not_fired(analysis, "location_unfamiliar")


class TestChannelUnfamiliar:
    def test_channel_never_used_in_accepted_pix_adds_points_weighted_by_the_history(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, payee, transaction_date, channel="web"))

        assert rule_hit(analysis, "channel_unfamiliar")["points"] == 5

    def test_channel_already_used_in_accepted_pix_adds_nothing(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, payee, transaction_date))

        assert_rule_not_fired(analysis, "channel_unfamiliar")

    def test_channel_is_compared_without_case(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, payee, transaction_date, channel="APP"))

        assert_rule_not_fired(analysis, "channel_unfamiliar")


class TestTwoFactorDeniedRecently:
    def test_denied_two_factor_adds_points_to_the_next_pix_within_24_hours(self):
        transaction_date = business_hours_today()
        payer, _, payload, _ = two_factor_pix(transaction_date)
        confirm_two_factor(payload["id"], "denied", transaction_date + timedelta(minutes=2))

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date + timedelta(hours=1)))

        assert rule_hit(analysis, "two_factor_denied_recently")["points"] == 30

    def test_denied_two_factor_older_than_24_hours_does_not_count(self):
        transaction_date = business_hours_today()
        payer, _, payload, _ = two_factor_pix(transaction_date)
        confirm_two_factor(payload["id"], "denied", transaction_date + timedelta(minutes=2))

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date + timedelta(hours=24, minutes=3)))

        assert_rule_not_fired(analysis, "two_factor_denied_recently")

    def test_confirmed_two_factor_adds_no_points(self):
        transaction_date = business_hours_today()
        payer, _, payload, _ = two_factor_pix(transaction_date)
        confirm_two_factor(payload["id"], "confirmed", transaction_date + timedelta(minutes=2))

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date + timedelta(hours=1)))

        assert_rule_not_fired(analysis, "two_factor_denied_recently")
