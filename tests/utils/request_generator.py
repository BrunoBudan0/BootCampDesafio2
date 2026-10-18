from os import environ

from tests.utils.requisition import ClientRequisition


INTERNAL_TOKEN = environ.get("INTERNAL_TOKEN", "default_token")
AUTHORIZED_HEADERS = {"INTERNAL-TOKEN": INTERNAL_TOKEN}


class RequestGenerator:
    @staticmethod
    def POST_pix_transaction(payload: dict) -> tuple:
        response = ClientRequisition.send("POST", "/pix/transaction", payload=payload, headers=AUTHORIZED_HEADERS)
        return response.response_status, response.response_json

    @staticmethod
    def GET_pix_transaction(pix_id: str) -> tuple:
        response = ClientRequisition.send("GET", f"/pix/transaction/{pix_id}", headers=AUTHORIZED_HEADERS)
        return response.response_status, response.response_json

    @staticmethod
    def POST_two_factor_confirmation(pix_id: str, payload: dict) -> tuple:
        response = ClientRequisition.send(
            "POST",
            f"/pix/transaction/{pix_id}/two-factor",
            payload=payload,
            headers=AUTHORIZED_HEADERS,
        )
        return response.response_status, response.response_json

    @staticmethod
    def POST_source_nightly_limit(document_number: str, payload: dict) -> tuple:
        response = ClientRequisition.send(
            "POST",
            f"/sources/{document_number}/nightly-limit",
            payload=payload,
            headers=AUTHORIZED_HEADERS,
        )
        return response.response_status, response.response_json

    @staticmethod
    def GET_risk_policy() -> tuple:
        response = ClientRequisition.send("GET", "/risk-policy", headers=AUTHORIZED_HEADERS)
        return response.response_status, response.response_json

    @staticmethod
    def GET_risk_policy_version(version) -> tuple:
        response = ClientRequisition.send("GET", f"/risk-policy/versions/{version}", headers=AUTHORIZED_HEADERS)
        return response.response_status, response.response_json

    @staticmethod
    def GET_risk_policy_templates() -> tuple:
        response = ClientRequisition.send("GET", "/risk-policy/templates", headers=AUTHORIZED_HEADERS)
        return response.response_status, response.response_json

    @staticmethod
    def GET_risk_policy_guardrails() -> tuple:
        response = ClientRequisition.send("GET", "/risk-policy/guardrails", headers=AUTHORIZED_HEADERS)
        return response.response_status, response.response_json

    @staticmethod
    def POST_risk_policy_version(payload: dict) -> tuple:
        response = ClientRequisition.send("POST", "/risk-policy/versions", payload=payload, headers=AUTHORIZED_HEADERS)
        return response.response_status, response.response_json

    @staticmethod
    def GET_system_logs(query_params: dict = None) -> tuple:
        response = ClientRequisition.send("GET", "/system-logs", headers=AUTHORIZED_HEADERS, query_params=query_params)
        return response.response_status, response.response_json
