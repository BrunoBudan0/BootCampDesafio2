from datetime import timedelta, timezone

from tests.utils.assertions import assert_rule_fired, assert_rule_not_fired, rule_hit
from tests.utils.clock import business_hours_today, iso, today_at
from tests.utils.pix_payload import (
    new_company_payee,
    new_company_payer,
    new_individual_payee,
    new_individual_payer,
    payer_on_another_device,
    pix_payload,
)
from tests.utils.request_generator import RequestGenerator
from tests.utils.scenario import (
    analyze,
    analyze_expecting,
    build_accepted_history,
    confirm_two_factor,
    fire_together,
    payer_with_accepted_history,
    payer_with_registered_device,
    setup_ok,
)


def first_pix_tonight(payer, payee, hour, amount_cents, minute=0):
    return analyze(pix_payload(payer, payee, today_at(hour, minute), amount_cents))


class TestNightlyLimit:
    def test_exactly_1000_reais_at_night_is_within_the_limit(self):
        analysis = first_pix_tonight(new_individual_payer(), new_individual_payee(), 23, 100000)

        assert_rule_not_fired(analysis, "nightly_limit_exceeded")

    def test_one_cent_above_1000_reais_at_night_is_rejected(self):
        analysis = first_pix_tonight(new_individual_payer(), new_individual_payee(), 23, 100001)

        assert analysis["status"] == "rejected"
        assert rule_hit(analysis, "nightly_limit_exceeded")["kind"] == "regulatory"

    def test_split_pix_in_the_same_night_add_up(self):
        payer, _ = payer_with_registered_device()
        analyze_expecting(pix_payload(payer, new_individual_payee(), today_at(21), 60000), "approved", "primeira parte da noite")

        analysis = analyze(pix_payload(payer, new_individual_payee(), today_at(23), 50000))

        assert_rule_fired(analysis, "nightly_limit_exceeded")

    def test_the_night_continues_after_midnight(self):
        payer, _ = payer_with_registered_device()
        analyze_expecting(pix_payload(payer, new_individual_payee(), today_at(23), 90000), "approved", "Pix antes da meia-noite")

        analysis = analyze(pix_payload(payer, new_individual_payee(), today_at(1) + timedelta(days=1), 20000))

        assert_rule_fired(analysis, "nightly_limit_exceeded")

    def test_each_night_has_its_own_limit(self):
        payer, _ = payer_with_registered_device()
        analyze_expecting(pix_payload(payer, new_individual_payee(), today_at(23), 90000), "approved", "Pix da primeira noite")

        analysis = analyze(pix_payload(payer, new_individual_payee(), today_at(21) + timedelta(days=1), 90000))

        assert_rule_not_fired(analysis, "nightly_limit_exceeded")

    def test_the_night_starts_at_20h(self):
        at_twenty = first_pix_tonight(new_individual_payer(), new_individual_payee(), 20, 150000)
        before_twenty = analyze(pix_payload(new_individual_payer(), new_individual_payee(), today_at(19, 59, 59), 150000))

        assert_rule_fired(at_twenty, "nightly_limit_exceeded")
        assert_rule_not_fired(before_twenty, "nightly_limit_exceeded")

    def test_the_night_ends_at_6h(self):
        at_six = first_pix_tonight(new_individual_payer(), new_individual_payee(), 6, 150000)
        before_six = analyze(pix_payload(new_individual_payer(), new_individual_payee(), today_at(5, 59, 59), 150000))

        assert_rule_not_fired(at_six, "nightly_limit_exceeded")
        assert_rule_fired(before_six, "nightly_limit_exceeded")

    def test_individual_paying_a_company_at_night_is_not_limited(self):
        analysis = first_pix_tonight(new_individual_payer(), new_company_payee(), 23, 500000)

        assert_rule_not_fired(analysis, "nightly_limit_exceeded")

    def test_company_paying_an_individual_at_night_is_not_limited(self):
        analysis = first_pix_tonight(new_company_payer(), new_individual_payee(), 23, 500000)

        assert_rule_not_fired(analysis, "nightly_limit_exceeded")

    def test_night_is_decided_by_the_offset_sent_in_the_pix(self):
        same_moment_in_sao_paulo = today_at(18)
        local_evening_in_utc = same_moment_in_sao_paulo.astimezone(timezone.utc)

        sent_with_utc_offset = analyze(pix_payload(new_individual_payer(), new_individual_payee(), local_evening_in_utc, 150000))
        sent_with_sao_paulo_offset = analyze(pix_payload(new_individual_payer(), new_individual_payee(), same_moment_in_sao_paulo, 150000))

        assert_rule_fired(sent_with_utc_offset, "nightly_limit_exceeded")
        assert_rule_not_fired(sent_with_sao_paulo_offset, "nightly_limit_exceeded")

    def test_pending_two_factor_uses_the_nightly_limit(self):
        night = today_at(23)
        payer, payee, _ = payer_with_accepted_history(business_hours_today() - timedelta(days=1), 1)
        analyze_expecting(pix_payload(payer_on_another_device(payer), payee, night, 90000), "two_factor_required", "Pix no aparelho novo à noite")

        analysis = analyze(pix_payload(payer, payee, night + timedelta(minutes=5), 20000))

        assert_rule_fired(analysis, "nightly_limit_exceeded")

    def test_expired_two_factor_stops_using_the_nightly_limit(self):
        night = today_at(23)
        payer, payee, _ = payer_with_accepted_history(business_hours_today() - timedelta(days=1), 1)
        analyze_expecting(pix_payload(payer_on_another_device(payer), payee, night, 90000), "two_factor_required", "Pix no aparelho novo à noite")

        analysis = analyze(pix_payload(payer, payee, night + timedelta(minutes=15), 20000))

        assert_rule_not_fired(analysis, "nightly_limit_exceeded")

    def test_rejected_pix_does_not_use_the_limit(self):
        payer = new_individual_payer()
        analyze_expecting(pix_payload(payer, new_individual_payee(), today_at(21), 150000), "rejected", "Pix que estoura o limite")

        analysis = analyze(pix_payload(payer, new_individual_payee(), today_at(22), 90000))

        assert_rule_not_fired(analysis, "nightly_limit_exceeded")

    def test_parallel_pix_in_the_same_night_cannot_both_pass(self):
        payer, _ = payer_with_registered_device()
        payloads = [pix_payload(payer, new_individual_payee(), today_at(23), 60000) for _ in range(2)]

        responses = fire_together([lambda payload=payload: RequestGenerator.POST_pix_transaction(payload) for payload in payloads])

        assert [status for status, _ in responses] == [201, 201]
        assert sorted(body["status"] for _, body in responses) == ["approved", "rejected"]


class TestUnregisteredDeviceLimit:
    def test_unregistered_device_above_200_reais_asks_two_factor(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)

        analysis = analyze(pix_payload(payer_on_another_device(payer), payee, transaction_date, 20001))

        assert_rule_fired(analysis, "unregistered_device_limit_exceeded")
        assert analysis["status"] == "two_factor_required"

    def test_unregistered_device_at_200_reais_is_within_the_limit(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)

        analysis = analyze(pix_payload(payer_on_another_device(payer), payee, transaction_date, 20000))

        assert_rule_not_fired(analysis, "unregistered_device_limit_exceeded")

    def test_daily_sum_on_an_unregistered_device_above_1000_reais_is_limited(self):
        morning = today_at(10)
        payer, payee = payer_with_registered_device()
        build_accepted_history(payer, payee, morning - timedelta(days=2), 5, amount_cents=30000)
        new_device_payer = payer_on_another_device(payer)
        last_small_pix = None
        for position in range(5):
            last_small_pix = analyze_expecting(
                pix_payload(new_device_payer, payee, morning + timedelta(minutes=10 * position), 19000),
                "approved",
                f"Pix pequeno no aparelho novo ({position + 1} de 5)",
            )

        analysis = analyze(pix_payload(new_device_payer, payee, morning + timedelta(minutes=50), 10000))

        assert_rule_not_fired(last_small_pix, "unregistered_device_limit_exceeded")
        assert_rule_fired(analysis, "unregistered_device_limit_exceeded")

    def test_daily_sum_restarts_at_local_midnight(self):
        late_evening = today_at(23)
        payer, payee = payer_with_registered_device(payee=new_company_payee())
        build_accepted_history(payer, payee, late_evening - timedelta(days=2), 5, amount_cents=30000)
        new_device_payer = payer_on_another_device(payer)
        for position in range(5):
            analyze(pix_payload(new_device_payer, payee, late_evening + timedelta(minutes=10 * position), 19000))

        analysis = analyze(pix_payload(new_device_payer, payee, today_at(0, 10) + timedelta(days=1), 19000))

        assert_rule_not_fired(analysis, "unregistered_device_limit_exceeded")

    def test_payer_without_accepted_pix_is_also_limited_above_200_reais(self):
        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today(), 20001))

        assert_rule_fired(analysis, "unregistered_device_limit_exceeded")
        assert analysis["status"] == "two_factor_required"

    def test_payer_without_accepted_pix_at_200_reais_is_within_the_limit(self):
        analysis = analyze(pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today(), 20000))

        assert_rule_not_fired(analysis, "unregistered_device_limit_exceeded")
        assert analysis["status"] == "approved"

    def test_device_of_the_first_accepted_pix_becomes_registered(self):
        transaction_date = business_hours_today()
        payer = new_individual_payer()
        analyze_expecting(pix_payload(payer, new_company_payee(), transaction_date - timedelta(days=1), 20000), "approved", "primeiro Pix aceito")

        same_device = analyze(pix_payload(payer, new_company_payee(), transaction_date, 50000))
        other_device = analyze(pix_payload(payer_on_another_device(payer), new_company_payee(), transaction_date + timedelta(minutes=1), 50000))

        assert_rule_not_fired(same_device, "unregistered_device_limit_exceeded")
        assert_rule_fired(other_device, "unregistered_device_limit_exceeded")

    def test_device_with_a_confirmed_two_factor_becomes_registered(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
        new_device_payer = payer_on_another_device(payer)
        payload = pix_payload(new_device_payer, payee, transaction_date, 30000)
        analyze_expecting(payload, "two_factor_required", "Pix no aparelho novo")
        confirm_two_factor(payload["id"], "confirmed", transaction_date + timedelta(minutes=2))

        analysis = analyze(pix_payload(new_device_payer, payee, transaction_date + timedelta(minutes=30), 30000))

        assert_rule_not_fired(analysis, "unregistered_device_limit_exceeded")

    def test_device_with_a_denied_two_factor_stays_unregistered(self):
        transaction_date = business_hours_today()
        payer, payee, _ = payer_with_accepted_history(transaction_date - timedelta(days=2), 1)
        new_device_payer = payer_on_another_device(payer)
        payload = pix_payload(new_device_payer, payee, transaction_date, 30000)
        analyze_expecting(payload, "two_factor_required", "Pix no aparelho novo")
        confirm_two_factor(payload["id"], "denied", transaction_date + timedelta(minutes=2))

        analysis = analyze(pix_payload(new_device_payer, payee, transaction_date + timedelta(minutes=30), 30000))

        assert_rule_fired(analysis, "unregistered_device_limit_exceeded")


class TestApprovedNightlyLimit:
    def test_raised_limit_only_applies_24_hours_after_the_request(self):
        payer = new_individual_payer()
        requested_at = today_at(22) - timedelta(days=1)
        status, body = RequestGenerator.POST_source_nightly_limit(
            payer.document_number,
            {"nightly_limit_cents": 500000, "requested_at": iso(requested_at)},
        )
        setup_ok(status, body, "aprovar o limite noturno de R$ 5.000", expected_statuses=(201,))

        before_effective = analyze(pix_payload(payer, new_individual_payee(), today_at(21, 59), 300000))
        after_effective = analyze(pix_payload(payer, new_individual_payee(), today_at(22, 1), 300000))

        assert_rule_fired(before_effective, "nightly_limit_exceeded")
        assert_rule_not_fired(after_effective, "nightly_limit_exceeded")

    def test_lowering_after_a_pending_raise_keeps_the_lower_limit(self):
        payer = new_individual_payer()
        raise_requested_at = today_at(9) - timedelta(days=1)
        for limit_cents, requested_at in ((500000, raise_requested_at), (50000, raise_requested_at + timedelta(hours=1))):
            status, body = RequestGenerator.POST_source_nightly_limit(
                payer.document_number,
                {"nightly_limit_cents": limit_cents, "requested_at": iso(requested_at)},
            )
            setup_ok(status, body, f"pedir o limite noturno de {limit_cents} centavos", expected_statuses=(201,))

        analysis = analyze(pix_payload(payer, new_individual_payee(), today_at(22), 60000))

        assert_rule_fired(analysis, "nightly_limit_exceeded")

    def test_lowered_limit_applies_immediately(self):
        payer = new_individual_payer()
        requested_at = today_at(20)
        status, body = RequestGenerator.POST_source_nightly_limit(
            payer.document_number,
            {"nightly_limit_cents": 50000, "requested_at": iso(requested_at)},
        )
        setup_ok(status, body, "reduzir o limite noturno para R$ 500", expected_statuses=(201,))

        analysis = analyze(pix_payload(payer, new_individual_payee(), today_at(21), 60000))

        assert_rule_fired(analysis, "nightly_limit_exceeded")
