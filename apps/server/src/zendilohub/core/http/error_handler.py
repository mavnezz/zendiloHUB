import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from zendilohub.core.domain.app_domain_error import AppDomainError, ErrorKind

STATUS_BY_KIND: dict[ErrorKind, int] = {
    'validation': 422,
    'unauthenticated': 401,
    'forbidden': 403,
    'not_found': 404,
    'conflict': 409,
    'too_large': 413,
    'unsupported': 415,
    'rate_limited': 429,
    'unavailable': 503,
    'upstream': 502,
}

CODE_BY_STATUS = {
    400: 'bad_request',
    401: 'unauthenticated',
    403: 'forbidden',
    404: 'not_found',
    405: 'method_not_allowed',
    413: 'too_large',
}

logger = logging.getLogger(__name__)


def error_body(code: str, message: str, params: Any = None) -> dict[str, Any]:
    """Every error leaves the API as `{ error, message }`, plus `params` for translated messages."""
    body: dict[str, Any] = {'error': code, 'message': message}
    if params:
        body['params'] = dict(params)
    return body


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppDomainError, _domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unexpected_error)


async def _domain_error(_request: Request, error: AppDomainError) -> JSONResponse:
    headers = {'Retry-After': str(error.params['retry_after'])} if 'retry_after' in error.params else None
    return JSONResponse(
        error_body(error.code, error.message, error.params), status_code=STATUS_BY_KIND[error.kind], headers=headers
    )


async def _validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    details = [
        {'field': '.'.join(str(part) for part in issue['loc'][1:]), 'message': issue['msg'], 'type': issue['type']}
        for issue in error.errors()
    ]
    body = error_body('invalid_request', 'The request is invalid')
    body['details'] = details
    return JSONResponse(body, status_code=422)


async def _http_error(_request: Request, error: HTTPException) -> JSONResponse:
    code = CODE_BY_STATUS.get(error.status_code, 'bad_request' if error.status_code < 500 else 'internal_error')
    return JSONResponse(error_body(code, str(error.detail)), status_code=error.status_code, headers=error.headers)


async def _unexpected_error(request: Request, error: Exception) -> JSONResponse:
    logger.error('Unhandled error', exc_info=error, extra={'method': request.method, 'path': request.url.path})
    return JSONResponse(error_body('internal_error', 'Internal server error'), status_code=500)
