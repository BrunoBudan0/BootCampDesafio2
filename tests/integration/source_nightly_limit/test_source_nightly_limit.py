from datetime import timedelta

import pytest

from tests.utils.assertions import assert_error
from tests.utils.clock import iso, parse_iso, today_at
from tests.utils.random_generator import RandomGenerator
from tests.utils.request_generator import RequestGenerator
from tests.utils.requisition import ClientRequisition
from tests.utils.scenario import assert_scenario_step_succeeded


def nightly_limit(limit_cents, requested_at):
    return {"nightly_limit_cents": limit_cents, "requested_at": iso(requested_at)}


class TestSourceNightlyLimit:
    def test_raised_limit_is_recorded_to_apply_24_hours_after_the_request(self):
        requested_at = today_at(9)

        status, body = RequestGenerator.POST_source_nightly_limit(RandomGenerator.generate_cpf(), nightly_limit(500000, requested_at))

        assert status == 201
        assert body["nightly_limit_cents"] == 500000
        assert parse_iso(body["requested_at"]) == requested_at
        assert parse_iso(body["effective_at"]) == requested_at + timedelta(hours=24)

    def test_lowered_limit_is_recorded_to_apply_at_the_request(self):
        requested_at = today_at(9)

        status, body = RequestGenerator.POST_source_nightly_limit(RandomGenerator.generate_cpf(), nightly_limit(50000, requested_at))

        assert status == 201
        assert parse_iso(body["effective_at"]) == requested_at

    def test_raise_or_lower_is_measured_against_the_limit_in_force_at_the_request(self):
        document_number = RandomGenerator.generate_cpf()
        first_request = today_at(9) - timedelta(days=3)
        status, body = RequestGenerator.POST_source_nightly_limit(document_number, nightly_limit(500000, first_request))
        assert_scenario_step_succeeded(status, body, "aprovar o limite noturno de R$ 5.000", expected_statuses=(201,))
        second_request = first_request + timedelta(days=2)

        status, body = RequestGenerator.POST_source_nightly_limit(document_number, nightly_limit(300000, second_request))

        assert status == 201
        assert parse_iso(body["effective_at"]) == second_request

    def test_document_without_punctuation_is_accepted(self):
        document_number = RandomGenerator.generate_cpf().replace(".", "").replace("-", "")

        status, body = RequestGenerator.POST_source_nightly_limit(document_number, nightly_limit(500000, today_at(9)))

        assert status == 201

    @pytest.mark.parametrize("company_document", [RandomGenerator.generate_cnpj(), RandomGenerator.generate_alphanumeric_cnpj()])
    def test_company_document_is_refused_with_422(self, company_document):
        status, body = RequestGenerator.POST_source_nightly_limit(company_document.replace("/", ""), nightly_limit(500000, today_at(9)))

        assert_error(status, body, 422, "QIT001010")

    def test_cpf_with_wrong_check_digits_is_refused_with_422(self):
        invalid_cpf = RandomGenerator.with_wrong_check_digit(RandomGenerator.generate_cpf())

        status, body = RequestGenerator.POST_source_nightly_limit(invalid_cpf, nightly_limit(500000, today_at(9)))

        assert_error(status, body, 422, "QIT001003")

    @pytest.mark.parametrize(
        "invalid_body",
        [
            {"nightly_limit_cents": 0, "requested_at": "2026-10-17T09:00:00-03:00"},
            {"nightly_limit_cents": "500000", "requested_at": "2026-10-17T09:00:00-03:00"},
            {"nightly_limit_cents": 500000},
            {"requested_at": "2026-10-17T09:00:00-03:00"},
            {"nightly_limit_cents": 500000, "requested_at": "2026-10-17T09:00:00"},
            {"nightly_limit_cents": 500000, "requested_at": "2026-10-17T09:00:00-03:00", "extra": 1},
        ],
    )
    def test_invalid_body_is_refused_with_400(self, invalid_body):
        status, body = RequestGenerator.POST_source_nightly_limit(RandomGenerator.generate_cpf(), invalid_body)

        assert_error(status, body, 400, "QIT000001")

    @pytest.mark.parametrize("impossible_date", ["2026-02-30T09:00:00-03:00", "9999-12-31T23:00:00+00:00"])
    def test_impossible_request_date_is_refused_with_422(self, impossible_date):
        status, body = RequestGenerator.POST_source_nightly_limit(
            RandomGenerator.generate_cpf(),
            {"nightly_limit_cents": 500000, "requested_at": impossible_date},
        )

        assert_error(status, body, 422, "QIT001004")

    def test_limit_without_internal_token_is_refused_with_403(self):
        response = ClientRequisition.send(
            "POST",
            f"/sources/{RandomGenerator.generate_cpf()}/nightly-limit",
            payload=nightly_limit(500000, today_at(9)),
        )

        assert_error(response.response_status, response.response_json, 403, "QIT000002")
