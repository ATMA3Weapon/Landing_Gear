from __future__ import annotations

import logging
import uuid
from typing import Any

from aiohttp import web

from .utils import sanitize_log_value


DEFAULT_CORRELATION_HEADER = 'X-Correlation-ID'
DEFAULT_REQUEST_HEADER = 'X-Request-ID'


def configure_logging(level: str = 'INFO') -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    )


@web.middleware
async def correlation_middleware(request: web.Request, handler):
    correlation_id = (
        request.headers.get(DEFAULT_CORRELATION_HEADER)
        or request.headers.get(DEFAULT_REQUEST_HEADER)
        or str(uuid.uuid4())
    )
    request['correlation_id'] = correlation_id
    request['request_id'] = correlation_id
    response = await handler(request)
    response.headers[DEFAULT_CORRELATION_HEADER] = correlation_id
    response.headers[DEFAULT_REQUEST_HEADER] = correlation_id
    return response


@web.middleware
async def request_logging_middleware(request: web.Request, handler):
    correlation_id = request.get('correlation_id') or request.get('request_id') or 'unknown'
    logger = logging.getLogger('landing_gear.http')
    logger.info('request started %s %s correlation_id=%s', request.method, request.path, correlation_id)
    response = await handler(request)
    logger.info(
        'request finished %s %s status=%s correlation_id=%s',
        request.method,
        request.path,
        response.status,
        correlation_id,
    )
    return response


def bind_logger_context(logger: logging.Logger, **fields: Any) -> logging.LoggerAdapter[Any]:
    return logging.LoggerAdapter(logger, extra=fields)
