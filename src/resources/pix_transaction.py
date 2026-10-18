from fastapi import Body, status
from fastapi.responses import JSONResponse

from controllers import PixAnalysisController
from utils.schema_handler import SchemaHandler


class PixTransactionResource:
    @SchemaHandler.validate("post_pix_transaction.json")
    def on_post(self, payload: dict = Body(...)) -> JSONResponse:
        status_code, analysis = PixAnalysisController().analyze(payload)

        return JSONResponse(content=analysis, status_code=status_code)

    def on_get(self, pix_id: str) -> JSONResponse:
        analysis = PixAnalysisController().get_analysis(pix_id)

        return JSONResponse(content=analysis, status_code=status.HTTP_200_OK)

    @SchemaHandler.validate("post_two_factor_confirmation.json")
    def on_post_two_factor(self, pix_id: str, payload: dict = Body(...)) -> JSONResponse:
        status_code, analysis = PixAnalysisController().confirm_two_factor(pix_id, payload)

        return JSONResponse(content=analysis, status_code=status_code)
