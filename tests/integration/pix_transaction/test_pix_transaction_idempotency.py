from datetime import timedelta, timezone

from tests.utils.assertions import assert_error, assert_rule_fired, assert_rule_not_fired
from tests.utils.clock import business_hours_today, iso
from tests.utils.pix_payload import new_individual_payee, new_individual_payer, pix_payload
from tests.utils.request_generator import RequestGenerator
from tests.utils.scenario import analyze, send_all_at_the_same_time


def reversed_keys(payload: dict) -> dict:
    return {key: reversed_keys(value) if isinstance(value, dict) else value for key, value in reversed(list(payload.items()))}


class TestPixTransactionIdempotency:
    def test_same_pix_sent_again_returns_the_recorded_analysis_with_200(self):
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())

        first_status, first_body = RequestGenerator.POST_pix_transaction(payload)
        second_status, second_body = RequestGenerator.POST_pix_transaction(payload)

        assert first_status == 201
        assert second_status == 200
        assert second_body == first_body

    def test_same_pix_with_fields_in_another_order_is_the_same_pix(self):
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())

        first_status, first_body = RequestGenerator.POST_pix_transaction(payload)
        second_status, second_body = RequestGenerator.POST_pix_transaction(reversed_keys(payload))

        assert first_status == 201
        assert second_status == 200
        assert second_body["key"] == first_body["key"]

    def test_same_pix_with_normalized_document_channel_and_amount_is_the_same_pix(self):
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())
        first_body = analyze(payload)
        normalized = dict(payload, amount=float(payload["amount"]))
        normalized["source_account"] = dict(
            payload["source_account"],
            owner={"document_number": payload["source_account"]["owner"]["document_number"].replace(".", "").replace("-", "")},
        )
        normalized["source"] = dict(payload["source"], channel=payload["source"]["channel"].upper())

        status, body = RequestGenerator.POST_pix_transaction(normalized)

        assert status == 200
        assert body == first_body

    def test_same_instant_with_another_offset_is_other_content(self):
        transaction_date = business_hours_today()
        payload = pix_payload(new_individual_payer(), new_individual_payee(), transaction_date)
        analyze(payload)
        same_instant_in_utc = dict(payload, transaction_date=iso(transaction_date.astimezone(timezone.utc)))

        status, body = RequestGenerator.POST_pix_transaction(same_instant_in_utc)

        assert_error(status, body, 409, "QIT001002")

    def test_same_id_with_other_content_is_refused_with_409_and_keeps_the_first_analysis(self):
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())
        first_body = analyze(payload)
        other_content = dict(payload, amount=payload["amount"] + 1)

        status, body = RequestGenerator.POST_pix_transaction(other_content)

        assert_error(status, body, 409, "QIT001002")
        get_status, recorded = RequestGenerator.GET_pix_transaction(payload["id"])
        assert get_status == 200
        assert recorded == first_body

    def test_parallel_copies_of_the_same_pix_create_a_single_analysis(self):
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())

        responses = send_all_at_the_same_time([lambda: RequestGenerator.POST_pix_transaction(payload) for _ in range(5)])

        statuses = sorted(status for status, _ in responses)
        assert statuses == [200, 200, 200, 200, 201]
        assert len({body["key"] for _, body in responses}) == 1

    def test_repeated_pix_does_not_count_as_a_new_attempt(self):
        payer = new_individual_payer()
        first_moment = business_hours_today()
        repeated_payload = pix_payload(payer, new_individual_payee(), first_moment)
        analyze(repeated_payload)
        for _ in range(3):
            RequestGenerator.POST_pix_transaction(repeated_payload)
        for minute in (1, 2):
            analyze(pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=minute)))

        fourth_attempt = analyze(pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=3)))
        fifth_attempt = analyze(pix_payload(payer, new_individual_payee(), first_moment + timedelta(minutes=4)))

        assert_rule_not_fired(fourth_attempt, "burst_of_pix")
        assert_rule_fired(fifth_attempt, "burst_of_pix")
