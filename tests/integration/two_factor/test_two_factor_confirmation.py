from datetime import timedelta

import pytest

from tests.utils.assertions import assert_error, assert_rule_fired, assert_rule_not_fired
from tests.utils.clock import business_hours_today, iso, parse_iso, today_at
from tests.utils.pix_payload import new_company_payee, new_individual_payee, new_individual_payer, pix_payload
from tests.utils.random_generator import RandomGenerator
from tests.utils.request_generator import RequestGenerator
from tests.utils.requisition import ClientRequisition
from tests.utils.scenario import analyze, analyze_expecting, answer_two_factor, send_all_at_the_same_time, new_account_pix_waiting_two_factor


def two_factor_answer_body(result, answered_at):
    return {"result": result, "answered_at": iso(answered_at)}


def assert_two_factor_still_unanswered(pix_id):
    status, body = RequestGenerator.GET_pix_transaction(pix_id)
    assert status == 200
    assert body["metadata"]["two_factor"]["status"] in ("pending", "expired")
    assert body["metadata"]["two_factor"]["answered_at"] is None


class TestTwoFactorConfirmation:
    @pytest.mark.parametrize("result", ["confirmed", "denied"])
    def test_result_is_recorded_with_201_and_shown_in_the_analysis(self, result):
        transaction_date = business_hours_today()
        _, _, payload, analysis = new_account_pix_waiting_two_factor(transaction_date)
        answered_at = transaction_date + timedelta(minutes=3)

        status, body = RequestGenerator.POST_two_factor_confirmation(payload["id"], two_factor_answer_body(result, answered_at))

        assert status == 201
        assert body["key"] == analysis["key"]
        assert body["status"] == "two_factor_required"
        assert body["metadata"]["two_factor"]["status"] == result
        assert parse_iso(body["metadata"]["two_factor"]["answered_at"]) == answered_at
        get_status, recorded = RequestGenerator.GET_pix_transaction(payload["id"])
        assert recorded == body

    def test_same_result_sent_again_returns_200_with_the_same_analysis(self):
        transaction_date = business_hours_today()
        _, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)
        first = answer_two_factor(payload["id"], "confirmed", transaction_date + timedelta(minutes=3))

        status, body = RequestGenerator.POST_two_factor_confirmation(
            payload["id"], two_factor_answer_body("confirmed", transaction_date + timedelta(minutes=3))
        )

        assert status == 200
        assert body == first

    def test_same_result_with_another_moment_keeps_the_first_confirmation(self):
        transaction_date = business_hours_today()
        _, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)
        first = answer_two_factor(payload["id"], "confirmed", transaction_date + timedelta(minutes=3))

        status, body = RequestGenerator.POST_two_factor_confirmation(
            payload["id"], two_factor_answer_body("confirmed", transaction_date + timedelta(minutes=5))
        )

        assert status == 200
        assert body == first

    def test_parallel_opposite_results_record_only_one(self):
        transaction_date = business_hours_today()
        _, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)
        answer_bodies = [two_factor_answer_body(result, transaction_date + timedelta(minutes=3)) for result in ("confirmed", "denied")]

        responses = send_all_at_the_same_time([lambda body=body: RequestGenerator.POST_two_factor_confirmation(payload["id"], body) for body in answer_bodies])

        assert sorted(status for status, _ in responses) == [201, 409]
        winning_analysis = next(body for status, body in responses if status == 201)
        get_status, recorded = RequestGenerator.GET_pix_transaction(payload["id"])
        assert get_status == 200
        assert recorded == winning_analysis

    def test_other_result_after_a_confirmation_is_refused_with_409_and_keeps_the_first(self):
        transaction_date = business_hours_today()
        _, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)
        first = answer_two_factor(payload["id"], "confirmed", transaction_date + timedelta(minutes=3))

        status, body = RequestGenerator.POST_two_factor_confirmation(
            payload["id"], two_factor_answer_body("denied", transaction_date + timedelta(minutes=4))
        )

        assert_error(status, body, 409, "QIT001008")
        get_status, recorded = RequestGenerator.GET_pix_transaction(payload["id"])
        assert recorded == first

    @pytest.mark.parametrize("decision", ["approved", "rejected"])
    def test_analysis_that_did_not_ask_two_factor_is_refused_with_409(self, decision):
        if decision == "approved":
            transaction_date = business_hours_today()
            payload = pix_payload(new_individual_payer(), new_individual_payee(), transaction_date)
        else:
            transaction_date = today_at(23)
            payload = pix_payload(new_individual_payer(), new_individual_payee(), transaction_date, 150000)
        before = analyze_expecting(payload, decision, f"Pix {decision}")

        status, body = RequestGenerator.POST_two_factor_confirmation(
            payload["id"], two_factor_answer_body("confirmed", transaction_date + timedelta(minutes=1))
        )

        assert_error(status, body, 409, "QIT001007")
        get_status, recorded = RequestGenerator.GET_pix_transaction(payload["id"])
        assert recorded == before

    def test_unknown_pix_is_refused_with_404(self):
        status, body = RequestGenerator.POST_two_factor_confirmation(
            RandomGenerator.generate_pix_id(), two_factor_answer_body("confirmed", business_hours_today())
        )

        assert_error(status, body, 404, "QIT001001")

    def test_pix_id_with_a_null_byte_is_refused_with_404(self):
        status, body = RequestGenerator.POST_two_factor_confirmation("pix%00id", two_factor_answer_body("confirmed", business_hours_today()))

        assert_error(status, body, 404, "QIT001001")

    def test_confirmation_after_the_validity_is_refused_with_422_and_not_recorded(self):
        transaction_date = business_hours_today()
        _, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)

        status, body = RequestGenerator.POST_two_factor_confirmation(
            payload["id"], two_factor_answer_body("confirmed", transaction_date + timedelta(minutes=10, seconds=1))
        )

        assert_error(status, body, 422, "QIT001009")
        assert_two_factor_still_unanswered(payload["id"])

    def test_confirmation_before_the_pix_is_refused_with_422_and_not_recorded(self):
        transaction_date = business_hours_today()
        _, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)

        status, body = RequestGenerator.POST_two_factor_confirmation(
            payload["id"], two_factor_answer_body("confirmed", transaction_date - timedelta(seconds=1))
        )

        assert_error(status, body, 422, "QIT001009")
        assert_two_factor_still_unanswered(payload["id"])

    def test_confirmation_at_the_last_second_of_the_validity_is_accepted(self):
        transaction_date = business_hours_today()
        _, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)

        status, body = RequestGenerator.POST_two_factor_confirmation(
            payload["id"], two_factor_answer_body("confirmed", transaction_date + timedelta(minutes=10))
        )

        assert status == 201
        assert body["metadata"]["two_factor"]["status"] == "confirmed"

    @pytest.mark.parametrize(
        "invalid_body",
        [
            {"result": "approved", "answered_at": "2026-10-17T22:20:00-03:00"},
            {"result": "confirmed"},
            {"answered_at": "2026-10-17T22:20:00-03:00"},
            {"result": "confirmed", "answered_at": "2026-10-17T22:20:00"},
            {"result": "confirmed", "answered_at": "2026-10-17T22:20:00-03:00", "extra": True},
        ],
    )
    def test_invalid_body_is_refused_with_400_and_not_recorded(self, invalid_body):
        _, _, payload, _ = new_account_pix_waiting_two_factor(business_hours_today())

        status, body = RequestGenerator.POST_two_factor_confirmation(payload["id"], invalid_body)

        assert_error(status, body, 400, "QIT000001")
        assert_two_factor_still_unanswered(payload["id"])

    def test_confirmation_without_internal_token_is_refused_with_403(self):
        transaction_date = business_hours_today()
        _, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)

        response = ClientRequisition.send(
            "POST",
            f"/pix/transaction/{payload['id']}/two-factor",
            payload=two_factor_answer_body("confirmed", transaction_date + timedelta(minutes=1)),
        )

        assert_error(response.response_status, response.response_json, 403, "QIT000002")
        assert_two_factor_still_unanswered(payload["id"])


class TestTwoFactorAndHistory:
    def test_confirmed_two_factor_enters_the_payer_history(self):
        transaction_date = business_hours_today()
        payer, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)
        answer_two_factor(payload["id"], "confirmed", transaction_date + timedelta(minutes=2))

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date + timedelta(hours=25), 100000))

        assert_rule_not_fired(analysis, "new_destination_above_usual_ceiling")

    def test_denied_two_factor_stays_out_of_the_payer_history(self):
        transaction_date = business_hours_today()
        payer, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)
        answer_two_factor(payload["id"], "denied", transaction_date + timedelta(minutes=2))

        analysis = analyze(pix_payload(payer, new_individual_payee(), transaction_date + timedelta(hours=25), 100000))

        assert_rule_fired(analysis, "new_destination_above_usual_ceiling")

    def test_confirmed_two_factor_registers_the_device(self):
        transaction_date = business_hours_today()
        payer, _, payload, _ = new_account_pix_waiting_two_factor(transaction_date)
        answer_two_factor(payload["id"], "confirmed", transaction_date + timedelta(minutes=2))

        same_device = analyze(pix_payload(payer, new_company_payee(), transaction_date + timedelta(hours=1), 30000))

        assert_rule_not_fired(same_device, "unregistered_device_limit_exceeded")
