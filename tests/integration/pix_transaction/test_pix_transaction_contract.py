import copy
from uuid import UUID

import pytest

from tests.utils.assertions import assert_error
from tests.utils.clock import business_hours_today, iso
from tests.utils.pix_payload import (
    new_company_payee,
    new_individual_payee,
    new_individual_payer,
    payee_owned_by,
    pix_payload,
)
from tests.utils.random_generator import RandomGenerator
from tests.utils.request_generator import RequestGenerator
from tests.utils.requisition import ClientRequisition


DECISIONS = {"approved", "two_factor_required", "rejected"}
METADATA_FIELDS = {"risk_score", "destination_risk", "policy", "rules", "alerts", "two_factor"}


def valid_payload() -> dict:
    return pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())


def changed(payload: dict, path: list, value) -> dict:
    changed_payload = copy.deepcopy(payload)
    node = changed_payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return changed_payload


def without(payload: dict, path: list) -> dict:
    changed_payload = copy.deepcopy(payload)
    node = changed_payload
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return changed_payload


def assert_nothing_was_recorded(pix_id: str) -> None:
    status, body = RequestGenerator.GET_pix_transaction(pix_id)
    assert status == 404, f"O Pix recusado não devia ficar gravado, mas o GET devolveu {status}: {body}"


class TestPixTransactionContract:
    def test_pix_without_internal_token_is_refused_with_403_and_not_recorded(self):
        payload = valid_payload()

        response = ClientRequisition.send("POST", "/pix/transaction", payload=payload)

        assert_error(response.response_status, response.response_json, 403, "QIT000002")
        assert_nothing_was_recorded(payload["id"])

    def test_challenge_example_payload_is_analyzed_with_201(self):
        payload = {
            "id": RandomGenerator.generate_pix_id(),
            "amount": 150000,
            "transaction_date": "2026-10-17T22:15:00-03:00",
            "source_account": {
                "branch": "0001",
                "account_number": "88213",
                "opening_date": "2025-03-02T10:00:00-03:00",
                "owner": {"document_number": "123.456.789-09"},
            },
            "destination_account": {
                "participant": "60701190",
                "branch": "3675",
                "account_number": "10442",
                "opening_date": "2026-10-10T09:00:00-03:00",
                "owner": {"document_number": "987.654.321-00"},
            },
            "source": {
                "device_id": "dvc-9f2c71a8",
                "channel": "app",
                "ip": "198.51.100.23",
                "geolocation": {"latitude": -23.56, "longitude": -46.65},
            },
        }

        status, body = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201
        assert body["status"] in DECISIONS

    def test_new_analysis_returns_uuid_key_known_status_and_full_metadata(self):
        status, body = RequestGenerator.POST_pix_transaction(valid_payload())

        assert status == 201
        assert set(body) == {"key", "status", "metadata"}
        assert str(UUID(body["key"])) == body["key"]
        assert body["status"] in DECISIONS
        assert set(body["metadata"]) == METADATA_FIELDS

    @pytest.mark.parametrize(
        "missing_path",
        [
            ["id"],
            ["amount"],
            ["transaction_date"],
            ["source_account"],
            ["source_account", "branch"],
            ["source_account", "account_number"],
            ["source_account", "opening_date"],
            ["source_account", "owner"],
            ["source_account", "owner", "document_number"],
            ["destination_account"],
            ["destination_account", "participant"],
            ["destination_account", "branch"],
            ["destination_account", "account_number"],
            ["destination_account", "opening_date"],
            ["destination_account", "owner", "document_number"],
            ["source"],
            ["source", "device_id"],
            ["source", "channel"],
            ["source", "ip"],
        ],
    )
    def test_missing_required_field_is_refused_with_400_and_not_recorded(self, missing_path):
        payload = valid_payload()

        status, body = RequestGenerator.POST_pix_transaction(without(payload, missing_path))

        assert_error(status, body, 400, "QIT000001")
        assert_nothing_was_recorded(payload["id"])

    @pytest.mark.parametrize(
        "path, invalid_value",
        [
            (["amount"], 0),
            (["amount"], -100),
            (["amount"], "150000"),
            (["amount"], 1500.5),
            (["amount"], 1000000000001),
            (["transaction_date"], "2026-10-17T22:15:00"),
            (["transaction_date"], "2026-10-17"),
            (["transaction_date"], "17/10/2026 22:15"),
            (["source_account", "opening_date"], "2025-03-02"),
            (["source_account", "branch"], "00a1"),
            (["source_account", "account_number"], ""),
            (["source_account", "owner", "document_number"], "123"),
            (["destination_account", "participant"], "6070119"),
            (["destination_account", "owner", "document_number"], "12.abc.345/01de-35"),
            (["source", "device_id"], "dispositivo com espaço"),
            (["source", "channel"], "app web"),
            (["source", "ip"], "not-an-ip"),
            (["source", "geolocation"], {"latitude": -23.56}),
            (["source", "geolocation"], {"latitude": 91, "longitude": -46.65}),
            (["source", "geolocation"], {"latitude": -23.56, "longitude": -181}),
            (["source", "geolocation"], {"latitude": -23.56, "longitude": -46.65, "altitude": 760}),
            (["id"], "pix/000123"),
            (["id"], ""),
            (["unexpected_field"], "anything"),
            (["source_account", "unexpected_field"], "anything"),
        ],
    )
    def test_invalid_field_is_refused_with_400_and_not_recorded(self, path, invalid_value):
        payload = valid_payload()

        status, body = RequestGenerator.POST_pix_transaction(changed(payload, path, invalid_value))

        assert_error(status, body, 400, "QIT000001")
        assert_nothing_was_recorded(payload["id"])

    @pytest.mark.parametrize(
        "path, impossible_date",
        [
            (["transaction_date"], "2026-02-30T10:00:00-03:00"),
            (["transaction_date"], "2026-10-17T25:00:00-03:00"),
            (["transaction_date"], "2026-10-17T10:00:00+25:00"),
            (["source_account", "opening_date"], "2025-13-01T10:00:00-03:00"),
            (["destination_account", "opening_date"], "2025-04-31T10:00:00-03:00"),
        ],
    )
    def test_date_that_does_not_exist_is_refused_with_422_and_not_recorded(self, path, impossible_date):
        payload = valid_payload()

        status, body = RequestGenerator.POST_pix_transaction(changed(payload, path, impossible_date))

        assert_error(status, body, 422, "QIT001004")
        assert_nothing_was_recorded(payload["id"])

    @pytest.mark.parametrize("invalid_ip", ["999.1.1.1", "10.0.0", "1:2:3", "::::::"])
    def test_ip_that_does_not_exist_is_refused_with_422_and_not_recorded(self, invalid_ip):
        payload = valid_payload()

        status, body = RequestGenerator.POST_pix_transaction(changed(payload, ["source", "ip"], invalid_ip))

        assert_error(status, body, 422, "QIT001005")
        assert_nothing_was_recorded(payload["id"])

    @pytest.mark.parametrize(
        "path, invalid_document",
        [
            (["source_account", "owner", "document_number"], RandomGenerator.with_wrong_check_digit(RandomGenerator.generate_cpf())),
            (["destination_account", "owner", "document_number"], RandomGenerator.with_wrong_check_digit(RandomGenerator.generate_cpf())),
            (["source_account", "owner", "document_number"], "111.111.111-11"),
            (["destination_account", "owner", "document_number"], RandomGenerator.with_wrong_check_digit(RandomGenerator.generate_cnpj())),
            (["destination_account", "owner", "document_number"], RandomGenerator.with_wrong_check_digit(RandomGenerator.generate_alphanumeric_cnpj())),
        ],
    )
    def test_document_with_wrong_check_digits_is_refused_with_422_and_not_recorded(self, path, invalid_document):
        payload = valid_payload()

        status, body = RequestGenerator.POST_pix_transaction(changed(payload, path, invalid_document))

        assert_error(status, body, 422, "QIT001003")
        assert_nothing_was_recorded(payload["id"])

    @pytest.mark.parametrize("account", ["source_account", "destination_account"])
    def test_account_opened_after_the_pix_is_refused_with_422_and_not_recorded(self, account):
        transaction_date = business_hours_today()
        payload = pix_payload(new_individual_payer(), new_individual_payee(), transaction_date)
        payload[account]["opening_date"] = iso(transaction_date.replace(year=transaction_date.year + 1))

        status, body = RequestGenerator.POST_pix_transaction(payload)

        assert_error(status, body, 422, "QIT001006")
        assert_nothing_was_recorded(payload["id"])

    def test_document_without_punctuation_is_accepted(self):
        payload = valid_payload()
        payload["source_account"]["owner"]["document_number"] = RandomGenerator.generate_cpf().replace(".", "").replace("-", "")

        status, body = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201

    def test_alphanumeric_cnpj_is_accepted(self):
        payee = new_company_payee()
        payload = pix_payload(new_individual_payer(), payee, business_hours_today())
        payload["destination_account"]["owner"]["document_number"] = RandomGenerator.generate_alphanumeric_cnpj()

        status, body = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201

    def test_ipv6_is_accepted(self):
        payload = changed(valid_payload(), ["source", "ip"], "2001:db8::1")

        status, body = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201

    @pytest.mark.parametrize("geolocation", [None, "absent"])
    def test_geolocation_is_optional(self, geolocation):
        payload = valid_payload()
        if geolocation == "absent":
            payload["source"].pop("geolocation", None)
        else:
            payload["source"]["geolocation"] = None

        status, body = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201

    def test_pix_to_own_document_in_another_bank_is_accepted(self):
        payer = new_individual_payer()

        status, body = RequestGenerator.POST_pix_transaction(pix_payload(payer, payee_owned_by(payer), business_hours_today()))

        assert status == 201
