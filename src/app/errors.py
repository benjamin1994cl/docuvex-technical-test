"""Formato de error único de la API (sección 5.5 del enunciado)."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("docuvex")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def unauthorized() -> ApiError:
    return ApiError(401, "UNAUTHORIZED", "Usuario no identificado.")


def not_found() -> ApiError:
    # Mismo cuerpo para "no existe" y "no autorizado" (regla S5).
    return ApiError(404, "NOT_FOUND", "Recurso no encontrado.")


def _response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return _response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # FastAPI responde 422 por defecto; el contrato pide 400.
        return _response(400, "VALIDATION_ERROR", "Solicitud inválida.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            e = not_found()
            return _response(e.status, e.code, e.message)
        if exc.status_code == 405:
            return _response(405, "METHOD_NOT_ALLOWED", "Método no permitido.")
        return _response(exc.status_code, "HTTP_ERROR", "Solicitud no procesable.")

    @app.exception_handler(Exception)
    async def internal_error(_: Request, exc: Exception):
        # Solo el tipo de la excepción: el mensaje podría contener datos (S6).
        log.error("error interno tipo=%s", type(exc).__name__)
        return _response(500, "INTERNAL_ERROR", "Error interno.")
