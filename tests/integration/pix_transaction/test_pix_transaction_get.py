import json
from datetime import timedelta

from tests.utils.assertions import assert_error
from tests.utils.clock import business_hours_today, now_in_sao_paulo, parse_iso
from tests.utils.pix_payload import new_individual_payee, new_individual_payer, pix_payload
from tests.utils.random_generator import RandomGenerator
from tests.utils.request_generator import RequestGenerator
from tests.utils.requisition import ClientRequisition
from tests.utils.scenario import analyze, two_factor_pix


class TestPixTransactionGet:
    def test_get_returns_the_same_analysis_the_post_returned(self):
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())
        posted = analyze(payload)

        status, body = RequestGenerator.GET_pix_transaction(payload["id"])

        assert status == 200
        assert body == posted

    def test_unknown_pix_returns_404_with_qit001001(self):
        status, body = RequestGenerator.GET_pix_transaction(RandomGenerator.generate_pix_id())

        assert_error(status, body, 404, "QIT001001")

    def test_get_without_internal_token_is_refused_with_403(self):
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())
        analyze(payload)

        response = ClientRequisition.send("GET", f"/pix/transaction/{payload['id']}")

        assert_error(response.response_status, response.response_json, 403, "QIT000002")

    def test_analysis_never_exposes_the_documents_of_payer_and_payee(self):
        payer = new_individual_payer()
        payee = new_individual_payee()
        payload = pix_payload(payer, payee, business_hours_today())
        analyze(payload)

        status, body = RequestGenerator.GET_pix_transaction(payload["id"])

        assert status == 200
        text = json.dumps(body)
        for document_number in (payer.document_number, payee.document_number):
            digits = document_number.replace(".", "").replace("-", "").replace("/", "")
            assert digits not in text
            assert document_number not in text

    def test_two_factor_inside_validity_is_shown_as_pending(self):
        transaction_date = now_in_sao_paulo() - timedelta(minutes=1)
        _, _, payload, _ = two_factor_pix(transaction_date)

        status, body = RequestGenerator.GET_pix_transaction(payload["id"])

        assert status == 200
        two_factor = body["metadata"]["two_factor"]
        assert two_factor["status"] == "pending"
        assert parse_iso(two_factor["expires_at"]) == transaction_date + timedelta(minutes=10)
        assert two_factor["confirmed_at"] is None

    def test_two_factor_after_validity_is_shown_as_expired(self):
        _, _, payload, _ = two_factor_pix(now_in_sao_paulo() - timedelta(days=1))

        status, body = RequestGenerator.GET_pix_transaction(payload["id"])

        assert status == 200
        assert body["metadata"]["two_factor"]["status"] == "expired"

    def test_approved_pix_has_no_two_factor_information(self):
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())
        analyze(payload)

        status, body = RequestGenerator.GET_pix_transaction(payload["id"])

        assert status == 200
        assert body["status"] == "approved"
        assert body["metadata"]["two_factor"] is None
