"""Enveloppe d'erreur AFNOR (`{errorCode, errorMessage}`) pour les routes exposées à
Odoo (§ 4.4) — les deux contrats officiels (Flow Service et Directory Service, cf.
`backend/docs/afnor-contracts/`) partagent le même schéma `Error` et les mêmes
exemples d'`errorCode` par statut HTTP, repris ici tels quels (pas d'invention) :
400→MISSING_REQUIRED_FIELD, 401→MISSING_TOKEN, 403→FORBIDDEN_ACCESS,
404→MISSING_RESOURCE, 408→REQUEST_TIMEOUT, 413→FILE_SIZE_EXCEEDED,
422→UNPROCESSABLE_ENTITY, 429→TOO_MANY_REQUESTS, 500→INTERNAL_ERROR,
501→NOT_IMPLEMENTED, 503→RESOURCE_ERROR.

N'affecte que les requêtes sous `/api/afnor/` — les erreurs IHM gardent le format
`HTTPException` standard FastAPI, inchangé."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse

_ERROR_CODE_BY_STATUS = {
    400: "MISSING_REQUIRED_FIELD",
    401: "MISSING_TOKEN",
    403: "FORBIDDEN_ACCESS",
    404: "MISSING_RESOURCE",
    408: "REQUEST_TIMEOUT",
    413: "FILE_SIZE_EXCEEDED",
    422: "UNPROCESSABLE_ENTITY",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    501: "NOT_IMPLEMENTED",
    503: "RESOURCE_ERROR",
}

_AFNOR_PREFIX = "/api/afnor/"


def register_afnor_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _afnor_http_exception_handler(request: Request, exc: HTTPException):
        if not request.url.path.startswith(_AFNOR_PREFIX):
            return await http_exception_handler(request, exc)

        detail = exc.detail
        if isinstance(detail, dict) and "errorCode" in detail:
            # Le détail est déjà au format `Error` (ex. proxy transparent qui relaie
            # tel quel une erreur JSON renvoyée par SuperPDP) : ne pas le retraiter.
            body = detail
        else:
            body = {
                "errorCode": _ERROR_CODE_BY_STATUS.get(exc.status_code, "INTERNAL_ERROR"),
                "errorMessage": str(detail) if detail else None,
            }
        return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)
