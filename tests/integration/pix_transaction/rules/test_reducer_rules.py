from datetime import timedelta

from tests.utils.assertions import assert_rule_not_fired, fired_rule_hit
from tests.utils.clock import business_hours_today
from tests.utils.pix_payload import new_individual_payee, new_individual_payer, payee_owned_by, pix_payload
from tests.utils.scenario import analyze, analyze_expecting, payer_with_accepted_history


class TestSameOwner:
    def test_pix_to_the_payer_own_document_subtracts_30_points(self):
        payer = new_individual_payer()

        analysis = analyze(pix_payload(payer, payee_owned_by(payer), business_hours_today()))

        assert fired_rule_hit(analysis, "same_owner")["points"] == -30

    def test_pix_to_another_document_is_not_same_owner(self):
        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today()))

        assert_rule_not_fired(analysis, "same_owner")


class TestKnownDestination:
    def test_destination_with_three_accepted_pix_subtracts_20_points(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 3)

        analysis = analyze(pix_payload(payer, payee, transaction_date))

        assert fired_rule_hit(analysis, "known_destination")["points"] == -20

    def test_destination_with_two_accepted_pix_is_not_known_yet(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 2)

        analysis = analyze(pix_payload(payer, payee, transaction_date))

        assert_rule_not_fired(analysis, "known_destination")


class TestLongRegisteredDevice:
    def test_device_registered_more_than_30_days_ago_subtracts_10_points(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer()
        analyze_expecting(pix_payload(payer, new_individual_payee(), transaction_date - timedelta(days=31)), "approved", "registrar o aparelho")

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date))

        assert fired_rule_hit(analysis, "long_registered_device")["points"] == -10

    def test_device_registered_exactly_30_days_ago_subtracts_10_points(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer()
        analyze_expecting(pix_payload(payer, new_individual_payee(), transaction_date - timedelta(days=30)), "approved", "registrar o aparelho")

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date))

        assert fired_rule_hit(analysis, "long_registered_device")["points"] == -10

    def test_device_registered_29_days_ago_is_not_old_enough(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer()
        analyze_expecting(pix_payload(payer, new_individual_payee(), transaction_date - timedelta(days=29)), "approved", "registrar o aparelho")

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date))

        assert_rule_not_fired(analysis, "long_registered_device")
