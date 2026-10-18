from controllers.base_controller import BaseController
from controllers.rules import required_datetime
from dtos import system_logs_response
from repositories import SystemLogRepository


DEFAULT_LIMIT = 50
EXACT_MATCH_FILTERS = ("level", "event", "request_id")


class SystemLogController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.system_log_repository = SystemLogRepository(self.context)

    def get_latest_logs(self, query_params: dict) -> dict:
        since = None
        if "since" in query_params:
            since = required_datetime(query_params["since"], "since")

        filters = {field_name: query_params[field_name] for field_name in EXACT_MATCH_FILTERS if field_name in query_params}
        limit = int(query_params.get("limit", DEFAULT_LIMIT))

        return system_logs_response(self.system_log_repository.find_latest(filters, since, limit))
