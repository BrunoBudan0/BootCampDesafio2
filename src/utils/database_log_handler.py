import logging
import sys
from contextvars import ContextVar

from models import SystemLog
from repositories import add_system_log_in_its_own_transaction
from utils.log_text import loggable_text, storable_text
from utils.request_context import NO_REQUEST_ID


SMALLEST_LEVEL_ALWAYS_RECORDED = logging.ERROR

_is_recording: ContextVar[bool] = ContextVar("is_recording_system_log", default=False)


def is_critical(record: logging.LogRecord) -> bool:
    return record.levelno >= SMALLEST_LEVEL_ALWAYS_RECORDED or getattr(record, "persist", False)


def stack_trace_of(record: logging.LogRecord):
    if not record.exc_info or record.exc_info[0] is None:
        return None

    return storable_text(logging.Formatter().formatException(record.exc_info))


def system_log_from(record: logging.LogRecord) -> SystemLog:
    return SystemLog(
        request_id=getattr(record, "request_id", NO_REQUEST_ID),
        level=record.levelname,
        event=getattr(record, "event", record.levelname.lower()),
        logger_name=record.name[:150],
        message=storable_text(record.getMessage()),
        http_method=getattr(record, "http_method", None),
        path=getattr(record, "http_path", None),
        http_status=getattr(record, "http_status", None),
        error_code=getattr(record, "error_code", None),
        details=getattr(record, "details", None),
        stack_trace=stack_trace_of(record),
    )


class DatabaseLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if not is_critical(record) or _is_recording.get():
            return

        recording_token = _is_recording.set(True)
        try:
            add_system_log_in_its_own_transaction(system_log_from(record))
        except Exception as error:
            sys.stderr.write(f"O log crítico não foi gravado no banco ({type(error).__name__}): {loggable_text(record.getMessage())}\n")
        finally:
            _is_recording.reset(recording_token)
