from models import SystemLog


def system_log_response(system_log: SystemLog) -> dict:
    return {
        "created_at": system_log.created_at.isoformat(),
        "level": system_log.level,
        "event": system_log.event,
        "request_id": system_log.request_id,
        "message": system_log.message,
        "http_method": system_log.http_method,
        "path": system_log.path,
        "http_status": system_log.http_status,
        "error_code": system_log.error_code,
        "details": system_log.details,
        "stack_trace": system_log.stack_trace,
    }


def system_logs_response(system_logs: list) -> dict:
    return {"logs": [system_log_response(system_log) for system_log in system_logs]}
