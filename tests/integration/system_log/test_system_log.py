import json
from uuid import uuid4

import pytest

from tests.utils.assertions import assert_error
from tests.utils.clock import business_hours_today
from tests.utils.pix_payload import new_individual_payee, new_individual_payer, pix_payload
from tests.utils.random_generator import RandomGenerator
from tests.utils.request_generator import INTERNAL_TOKEN, RequestGenerator
from tests.utils.requisition import ClientRequisition
from tests.utils.scenario import restore_balanced_bank_policy


SYSTEM_LOG_FIELDS = {
    "created_at",
    "level",
    "event",
    "request_id",
    "message",
    "http_method",
    "path",
    "http_status",
    "error_code",
    "details",
    "stack_trace",
}
RISK_ACKNOWLEDGEMENT = {"requested_by": "analista.risco@banco.com.br", "risk_acknowledged": True}
WRONG_TOKEN = "token-errado-que-nao-pode-ir-para-o-log"


def new_request_id() -> str:
    return f"teste-{uuid4().hex}"


def send_with_request_id(method: str, endpoint: str, request_id: str, payload=None, token: str = INTERNAL_TOKEN):
    return ClientRequisition.send(method, endpoint, payload=payload, headers={"INTERNAL-TOKEN": token, "X-Request-ID": request_id})


def recorded_logs(request_id: str) -> list:
    status, body = RequestGenerator.GET_system_logs({"request_id": request_id})
    assert status == 200, f"Esperava HTTP 200 ao ler o log e veio {status}: {body}"
    return body["logs"]


def only_recorded_log(request_id: str) -> dict:
    logs = recorded_logs(request_id)
    assert len(logs) == 1, f"Esperava um registro crítico para {request_id} e vieram {len(logs)}: {logs}"
    assert set(logs[0]) == SYSTEM_LOG_FIELDS
    return logs[0]


@pytest.fixture
def restore_bank_policy():
    yield
    restore_balanced_bank_policy()


class TestCriticalLogsAreRecorded:
    def test_wrong_token_is_recorded_as_access_denied_without_the_token(self):
        request_id = new_request_id()

        response = send_with_request_id("GET", "/risk-policy", request_id, token=WRONG_TOKEN)

        assert_error(response.response_status, response.response_json, 403, "QIT000002")
        recorded_log = only_recorded_log(request_id)
        assert recorded_log["level"] == "WARNING"
        assert recorded_log["event"] == "access_denied"
        assert recorded_log["http_method"] == "GET"
        assert recorded_log["path"] == "/risk-policy"
        assert recorded_log["http_status"] == 403
        assert recorded_log["error_code"] == "QIT000002"
        assert WRONG_TOKEN not in json.dumps(recorded_log)

    def test_document_in_the_path_is_masked_in_the_record(self):
        request_id = new_request_id()
        document_number = RandomGenerator.generate_cpf()

        send_with_request_id("POST", f"/sources/{document_number}/nightly-limit", request_id, payload={}, token=WRONG_TOKEN)

        recorded_log = only_recorded_log(request_id)
        assert recorded_log["path"] == "/sources/***/nightly-limit"
        assert document_number not in json.dumps(recorded_log)

    def test_new_policy_version_is_recorded_with_who_asked(self, restore_bank_policy):
        request_id = new_request_id()

        response = send_with_request_id(
            "POST",
            "/risk-policy/versions",
            request_id,
            payload={"change_reason": "Reprova mais tarde", "parameters": {"rejection_score_threshold": 75}, **RISK_ACKNOWLEDGEMENT},
        )

        assert response.response_status == 201
        recorded_log = only_recorded_log(request_id)
        assert recorded_log["level"] == "INFO"
        assert recorded_log["event"] == "policy_version_created"
        assert recorded_log["http_method"] == "POST"
        assert recorded_log["path"] == "/risk-policy/versions"
        assert recorded_log["details"] == {
            "version": response.response_json["version"],
            "based_on": response.response_json["based_on"],
            "change_reason": "Reprova mais tarde",
            "requested_by": RISK_ACKNOWLEDGEMENT["requested_by"],
            "risk_acknowledged": True,
        }

    @pytest.mark.parametrize(
        "unsafe_edit, expected_code",
        [
            ({"change_reason": "Reprova só no extremo", "parameters": {"rejection_score_threshold": 85}, **RISK_ACKNOWLEDGEMENT}, "QIT001018"),
            ({"change_reason": "Desliga a fazenda de aparelhos", "rules": [{"code": "device_used_by_many_sources", "enabled": False}], **RISK_ACKNOWLEDGEMENT}, "QIT001018"),
            ({"change_reason": "Reprova mais tarde", "parameters": {"rejection_score_threshold": 75}}, "QIT001020"),
        ],
    )
    def test_unsafe_policy_edit_is_recorded_as_a_refusal(self, unsafe_edit, expected_code):
        request_id = new_request_id()

        response = send_with_request_id("POST", "/risk-policy/versions", request_id, payload=unsafe_edit)

        assert_error(response.response_status, response.response_json, 422, expected_code)
        recorded_log = only_recorded_log(request_id)
        assert recorded_log["level"] == "WARNING"
        assert recorded_log["event"] == "request_refused"
        assert recorded_log["http_status"] == 422
        assert recorded_log["error_code"] == expected_code


class TestRoutineEventsStayOutOfTheDatabase:
    def test_analyzed_pix_is_not_recorded(self):
        request_id = new_request_id()
        payload = pix_payload(new_individual_payer(), new_individual_payee(), business_hours_today())

        response = send_with_request_id("POST", "/pix/transaction", request_id, payload=payload)

        assert response.response_status == 201
        assert recorded_logs(request_id) == []

    def test_ordinary_refusal_is_not_recorded(self):
        request_id = new_request_id()

        response = send_with_request_id("GET", f"/pix/transaction/{RandomGenerator.generate_pix_id()}", request_id)

        assert_error(response.response_status, response.response_json, 404, "QIT001001")
        assert recorded_logs(request_id) == []


class TestReadSystemLogs:
    def test_logs_come_newest_first_and_respect_the_limit(self):
        request_ids = [new_request_id() for _ in range(3)]
        for request_id in request_ids:
            send_with_request_id("GET", "/risk-policy", request_id, token=WRONG_TOKEN)

        status, body = RequestGenerator.GET_system_logs({"event": "access_denied", "limit": "2"})

        assert status == 200
        assert [recorded_log["request_id"] for recorded_log in body["logs"]] == [request_ids[2], request_ids[1]]

    def test_level_filter_returns_only_that_level(self):
        send_with_request_id("GET", "/risk-policy", new_request_id(), token=WRONG_TOKEN)

        status, body = RequestGenerator.GET_system_logs({"level": "WARNING"})

        assert status == 200
        assert body["logs"]
        assert {recorded_log["level"] for recorded_log in body["logs"]} == {"WARNING"}

    def test_since_filter_leaves_out_older_logs(self):
        send_with_request_id("GET", "/risk-policy", new_request_id(), token=WRONG_TOKEN)

        status, body = RequestGenerator.GET_system_logs({"since": "2999-01-01T00:00:00-03:00"})

        assert status == 200
        assert body["logs"] == []

    @pytest.mark.parametrize(
        "invalid_query",
        [
            {"level": "LOUD"},
            {"limit": "0"},
            {"limit": "201"},
            {"limit": "abc"},
            {"request_id": "com espaço"},
            {"unknown": "1"},
        ],
    )
    def test_invalid_filter_is_refused_with_400(self, invalid_query):
        status, body = RequestGenerator.GET_system_logs(invalid_query)

        assert_error(status, body, 400, "QIT000001")

    def test_impossible_since_date_is_refused_with_422(self):
        status, body = RequestGenerator.GET_system_logs({"since": "2026-02-30T00:00:00-03:00"})

        assert_error(status, body, 422, "QIT001004")

    def test_reading_logs_without_internal_token_is_refused_with_403(self):
        response = ClientRequisition.send("GET", "/system-logs")

        assert_error(response.response_status, response.response_json, 403, "QIT000002")
