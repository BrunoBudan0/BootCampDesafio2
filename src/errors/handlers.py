import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from errors.base_error import (
    QIException,
    InternalError,
    InvalidParameter,
    InvalidSchema,
    MethodNotAllowed,
    NotFoundResource,
)
from utils.log_text import loggable_path, loggable_text
from utils.logger import get_logger


logger = get_logger(__name__)


def qi_exception_to_response(exception: QIException) -> JSONResponse:
    """Traduz um erro nosso para a resposta JSON que o cliente recebe.

    Este é o único lugar do projeto que sabe como um erro vira HTTP.
    Trocar de framework significa reescrever esta função — e mais nada.
    """
    body = {
        "title": exception.title,
        "description": exception.description,
        "translation": exception.translation,
        "code": exception.code,
    }
    return JSONResponse(status_code=exception.http_status, content=body)


def refusal_response(exception: QIException) -> JSONResponse:
    log_level = logging.ERROR if exception.http_status >= 500 else logging.WARNING
    logger.log(
        log_level,
        f"RECUSA {exception.code} {exception.http_status}: {loggable_text(exception.description)}",
        extra={
            "event": "request_refused",
            "persist": getattr(exception, "recorded_in_system_log", False),
            "http_status": exception.http_status,
            "error_code": exception.code,
        },
    )
    return qi_exception_to_response(exception)


def describe_validation_error(error: dict) -> str:
    location = []
    for part in error.get("loc", []):
        if part not in ("body", "query"):
            location.append(str(part))

    message = error.get("msg", "invalid value")

    if location:
        return f"{message} in {'.'.join(location)}"

    return message


def register_error_handlers(application: FastAPI) -> None:
    """Ensina a aplicação a responder cada tipo de erro."""

    @application.exception_handler(QIException)
    def handle_qi_exception(request: Request, exception: QIException) -> JSONResponse:
        return refusal_response(exception)

    @application.exception_handler(StarletteHTTPException)
    def handle_http_exception(request: Request, exception: StarletteHTTPException) -> JSONResponse:
        if exception.status_code == 404:
            return refusal_response(NotFoundResource())

        if exception.status_code == 405:
            return refusal_response(MethodNotAllowed())

        if exception.status_code == 400:
            return refusal_response(InvalidSchema(str(exception.detail)))

        logger.error(
            f"HTTP {exception.status_code} em {loggable_path(request.url.path)}: {loggable_text(str(exception.detail))}",
            extra={"event": "unexpected_error", "http_status": InternalError().http_status, "error_code": InternalError.code},
        )
        return qi_exception_to_response(InternalError())

    @application.exception_handler(RequestValidationError)
    def handle_validation_error(request: Request, exception: RequestValidationError) -> JSONResponse:
        errors = exception.errors()

        if errors:
            first_error = errors[0]
        else:
            first_error = {}

        description = describe_validation_error(first_error)
        origin = first_error.get("loc", [""])[0]

        # Este ramo NAO e alcancado hoje, e vale saber por que — e a
        # unica pista de que existem duas validacoes neste projeto, nao
        # uma.
        #
        # Quem julga a query string aqui e o JSON Schema, antes do
        # FastAPI (veja utils/schema_handler.py). Um ?page=-3 morre la,
        # com 400 QIT000001 — nunca chega a virar RequestValidationError.
        # E os parametros de endereco sao todos `str`, que nao tem como
        # falhar validacao.
        #
        # O ramo fica de pe para o dia em que alguma rota declarar um
        # parametro tipado (page: int) e passar a depender do FastAPI
        # para isso. O QIT000010 que o cliente ve hoje vem de outro
        # lugar: do controller, quando birthdate_from > birthdate_to.
        if origin in ("query", "path"):
            return refusal_response(InvalidParameter(description))

        return refusal_response(InvalidSchema(description))

    @application.exception_handler(Exception)
    def handle_unexpected_error(request: Request, exception: Exception) -> JSONResponse:
        logger.error(
            f"Erro inesperado em {request.method} {loggable_path(request.url.path)}",
            exc_info=exception,
            extra={"event": "unexpected_error", "http_status": InternalError().http_status, "error_code": InternalError.code},
        )
        return qi_exception_to_response(InternalError())
