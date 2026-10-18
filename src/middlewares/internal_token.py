import hmac

from fastapi import FastAPI, Request

from constants import BYPASS_ENDPOINTS, INTERNAL_TOKEN
from errors.base_error import ForbiddenNotInternal
from errors.handlers import qi_exception_to_response
from utils.logger import get_logger


logger = get_logger(__name__)


def register_internal_token_middleware(application: FastAPI) -> None:
    """Deixa passar só quem manda o header INTERNAL-TOKEN com o valor certo.

    O valor certo vem da variável de ambiente INTERNAL_TOKEN, nunca do
    código. As rotas de BYPASS_ENDPOINTS (raiz e health check) são públicas.

    Repare que aqui a gente DEVOLVE a resposta de erro em vez de levantar
    a exceção: dentro de um middleware, ninguém está escutando pra traduzir
    o erro — quem traduz são os exception handlers, que rodam mais pra
    dentro. Levantar aqui viraria um 500.
    """

    @application.middleware("http")
    async def check_internal_token(request: Request, call_next):
        is_public = request.url.path in BYPASS_ENDPOINTS

        if request.method == "OPTIONS" or is_public:
            return await call_next(request)

        received_token = request.headers.get("INTERNAL-TOKEN", "")
        if not hmac.compare_digest(received_token.encode(), INTERNAL_TOKEN.encode()):
            refusal = ForbiddenNotInternal()
            logger.warning(
                f"ACESSO NEGADO: INTERNAL-TOKEN ausente ou errado ({refusal.code})",
                extra={"event": "access_denied", "persist": True, "http_status": refusal.http_status, "error_code": refusal.code},
            )
            return qi_exception_to_response(refusal)

        return await call_next(request)
