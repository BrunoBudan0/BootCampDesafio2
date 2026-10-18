from fastapi import Body, status
from fastapi.responses import JSONResponse

from controllers import RiskPolicyController
from utils.schema_handler import SchemaHandler


class RiskPolicyResource:
    def on_get(self) -> JSONResponse:
        policy = RiskPolicyController().get_current_bank_policy()

        return JSONResponse(content=policy, status_code=status.HTTP_200_OK)

    def on_get_version(self, version: str) -> JSONResponse:
        policy = RiskPolicyController().get_bank_policy_version(version)

        return JSONResponse(content=policy, status_code=status.HTTP_200_OK)

    def on_get_templates(self) -> JSONResponse:
        templates = RiskPolicyController().get_templates()

        return JSONResponse(content=templates, status_code=status.HTTP_200_OK)

    @SchemaHandler.validate("post_risk_policy_version.json")
    def on_post_version(self, payload: dict = Body(...)) -> JSONResponse:
        policy = RiskPolicyController().create_bank_policy_version(payload)

        return JSONResponse(content=policy, status_code=status.HTTP_201_CREATED)
