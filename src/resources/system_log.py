from fastapi import Request, status
from fastapi.responses import JSONResponse

from controllers import SystemLogController
from utils.schema_handler import SchemaHandler


class SystemLogResource:
    @SchemaHandler.validate_query_params("get_system_logs.json")
    def on_get(self, request: Request) -> JSONResponse:
        system_logs = SystemLogController().get_latest_logs(dict(request.query_params))

        return JSONResponse(content=system_logs, status_code=status.HTTP_200_OK)
