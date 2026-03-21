from __future__ import annotations

from typing import Any, Mapping

from aiohttp import web


ResponseMeta = Mapping[str, Any] | None


def _base_meta(*, meta: ResponseMeta = None, correlation_id: str | None = None) -> dict[str, Any] | None:
    payload_meta = dict(meta or {})
    if correlation_id:
        payload_meta.setdefault('correlation_id', correlation_id)
    return payload_meta or None


def json_response(
    result: Any,
    *,
    status: int = 200,
    meta: ResponseMeta = None,
    correlation_id: str | None = None,
) -> web.Response:
    payload: dict[str, Any] = {'ok': True, 'result': result}
    final_meta = _base_meta(meta=meta, correlation_id=correlation_id)
    if final_meta:
        payload['meta'] = final_meta
    return web.json_response(payload, status=status)


def json_created(
    result: Any,
    *,
    meta: ResponseMeta = None,
    correlation_id: str | None = None,
) -> web.Response:
    return json_response(result, status=201, meta=meta, correlation_id=correlation_id)


def json_accepted(
    result: Any,
    *,
    meta: ResponseMeta = None,
    correlation_id: str | None = None,
) -> web.Response:
    return json_response(result, status=202, meta=meta, correlation_id=correlation_id)


def json_operation(
    operation: str,
    *,
    status_text: str = 'ok',
    result: Any = None,
    meta: ResponseMeta = None,
    correlation_id: str | None = None,
    status: int = 200,
) -> web.Response:
    payload_result: dict[str, Any] = {'operation': operation, 'status': status_text}
    if result is not None:
        payload_result['data'] = result
    return json_response(payload_result, status=status, meta=meta, correlation_id=correlation_id)


def json_collection(
    items: list[Any],
    *,
    item_name: str = 'items',
    total: int | None = None,
    meta: ResponseMeta = None,
    correlation_id: str | None = None,
    status: int = 200,
    limit: int | None = None,
    offset: int | None = None,
) -> web.Response:
    result: dict[str, Any] = {item_name: items, 'count': len(items)}
    if total is not None:
        result['total'] = total
    final_meta = dict(meta or {})
    if limit is not None or offset is not None:
        final_meta.setdefault('pagination', {})
        if limit is not None:
            final_meta['pagination']['limit'] = limit
        if offset is not None:
            final_meta['pagination']['offset'] = offset
        if total is not None and limit is not None and offset is not None:
            final_meta['pagination']['has_more'] = (offset + len(items)) < total
    return json_response(result, status=status, meta=final_meta or None, correlation_id=correlation_id)


def json_no_content() -> web.Response:
    return web.Response(status=204)


def json_error(
    message: str,
    *,
    status: int = 400,
    code: str | None = None,
    details: Any = None,
    meta: ResponseMeta = None,
    correlation_id: str | None = None,
) -> web.Response:
    payload: dict[str, Any] = {'ok': False, 'error': message}
    if code:
        payload['code'] = code
    if details is not None:
        payload['details'] = details
    final_meta = _base_meta(meta=meta, correlation_id=correlation_id)
    if final_meta:
        payload['meta'] = final_meta
    return web.json_response(payload, status=status)
