from fastapi import Body, status
from fastapi.responses import JSONResponse

from controllers import SourceController
from utils.schema_handler import SchemaHandler


class SourceResource:
    @SchemaHandler.validate("post_source_nightly_limit.json")
    def on_post_nightly_limit(self, document_number: str, payload: dict = Body(...)) -> JSONResponse:
        nightly_limit = SourceController().create_nightly_limit(document_number, payload)

        return JSONResponse(content=nightly_limit, status_code=status.HTTP_201_CREATED)
