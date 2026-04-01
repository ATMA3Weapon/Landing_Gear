from __future__ import annotations

from typing import Any, Iterable, NoReturn
from urllib.parse import urlparse

from aiohttp import web

from .errors import BadRequestError


DEFAULT_JSON_MAX_BYTES = 1024 * 1024
_SAFE_IDENTIFIER_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-')
_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_FALSE_VALUES = {'0', 'false', 'no', 'off'}


def _raise(message: str, *, code: str = 'bad_request') -> NoReturn:
    raise BadRequestError(message, code=code)


def _bounded_text(value: Any, *, field: str, max_len: int, strip: bool = True, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        _raise(f'{field} must be a string', code='invalid_field_type')
    text = value.strip() if strip else value
    if not text and not allow_empty:
        _raise(f'{field} must not be empty', code='invalid_field_value')
    if len(text) > max_len:
        _raise(f'{field} exceeds max length {max_len}', code='field_too_long')
    return text


def _query_values(request: web.Request, name: str) -> list[str]:
    return list(request.query.getall(name, []))


def _single_query_value(request: web.Request, name: str, *, required: bool = False, default: str | None = None) -> str | None:
    values = _query_values(request, name)
    if not values:
        if required:
            _raise(f'query parameter {name} is required', code='missing_query_parameter')
        return default
    if len(values) > 1:
        _raise(f'query parameter {name} must not be repeated', code='duplicate_query_parameter')
    return values[0]


async def read_json(request: web.Request, *, max_bytes: int = DEFAULT_JSON_MAX_BYTES) -> dict[str, Any]:
    content_length = request.content_length
    if content_length is not None and content_length > max_bytes:
        _raise(f'request body exceeds max size {max_bytes} bytes', code='request_too_large')
    try:
        payload = await request.json()
    except Exception as exc:
        _raise(f'invalid json body: {exc}', code='invalid_json')
    if not isinstance(payload, dict):
        _raise('json body must be an object', code='invalid_json_type')
    return payload


def reject_unknown_fields(payload: dict[str, Any], *, allowed: Iterable[str]) -> None:
    allowed_set = set(allowed)
    unknown = sorted(key for key in payload.keys() if key not in allowed_set)
    if unknown:
        _raise(f'unknown fields: {", ".join(unknown)}', code='unknown_fields')


def require_fields(payload: dict[str, Any], *field_names: str) -> None:
    missing = [name for name in field_names if name not in payload]
    if missing:
        _raise(f'missing required fields: {", ".join(missing)}', code='missing_fields')


def get_str(payload: dict[str, Any], field: str, *, required: bool = False, default: str | None = None, max_len: int = 256, allow_empty: bool = False) -> str | None:
    value = payload.get(field, default)
    if value is None:
        if required:
            _raise(f'{field} is required', code='missing_field')
        return None
    return _bounded_text(value, field=field, max_len=max_len, allow_empty=allow_empty)


def get_identifier(payload: dict[str, Any], field: str, *, required: bool = False, default: str | None = None, max_len: int = 128) -> str | None:
    value = get_str(payload, field, required=required, default=default, max_len=max_len)
    if value is None:
        return None
    if any(ch not in _SAFE_IDENTIFIER_CHARS for ch in value):
        _raise(f'{field} contains invalid characters', code='invalid_identifier')
    return value


def ensure_identifier_value(value: str, *, field: str = 'value', max_len: int = 128) -> str:
    text = _bounded_text(value, field=field, max_len=max_len)
    if any(ch not in _SAFE_IDENTIFIER_CHARS for ch in text):
        _raise(f'{field} contains invalid characters', code='invalid_identifier')
    return text


def get_enum(payload: dict[str, Any], field: str, *, allowed: Iterable[str], required: bool = False, default: str | None = None, max_len: int = 64) -> str | None:
    value = get_str(payload, field, required=required, default=default, max_len=max_len)
    if value is None:
        return None
    allowed_set = set(allowed)
    if value not in allowed_set:
        _raise(f'{field} must be one of: {", ".join(sorted(allowed_set))}', code='invalid_enum')
    return value


def get_mapping(payload: dict[str, Any], field: str, *, required: bool = False) -> dict[str, Any]:
    value = payload.get(field)
    if value is None:
        if required:
            _raise(f'{field} is required', code='missing_field')
        return {}
    if not isinstance(value, dict):
        _raise(f'{field} must be an object', code='invalid_field_type')
    return value


def get_list_of_str(payload: dict[str, Any], field: str, *, required: bool = False, max_items: int = 64, item_max_len: int = 128) -> list[str]:
    value = payload.get(field)
    if value is None:
        if required:
            _raise(f'{field} is required', code='missing_field')
        return []
    if not isinstance(value, list):
        _raise(f'{field} must be a list', code='invalid_field_type')
    if len(value) > max_items:
        _raise(f'{field} exceeds max item count {max_items}', code='field_too_large')
    result: list[str] = []
    for idx, item in enumerate(value):
        result.append(_bounded_text(item, field=f'{field}[{idx}]', max_len=item_max_len))
    return result


def get_query_str(request: web.Request, name: str, *, required: bool = False, default: str | None = None, max_len: int = 256, allow_empty: bool = False) -> str | None:
    value = _single_query_value(request, name, required=required, default=default)
    if value is None:
        return None
    return _bounded_text(value, field=f'query parameter {name}', max_len=max_len, allow_empty=allow_empty)


def get_query_int(request: web.Request, name: str, *, required: bool = False, default: int | None = None, min_value: int | None = None, max_value: int | None = None) -> int | None:
    raw = _single_query_value(request, name, required=required, default=None)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        _raise(f'query parameter {name} must be an integer', code='invalid_query_parameter')
    if min_value is not None and value < min_value:
        _raise(f'query parameter {name} must be >= {min_value}', code='invalid_query_parameter')
    if max_value is not None and value > max_value:
        _raise(f'query parameter {name} must be <= {max_value}', code='invalid_query_parameter')
    return value


def get_query_bool(request: web.Request, name: str, *, required: bool = False, default: bool | None = None) -> bool | None:
    raw = _single_query_value(request, name, required=required, default=None)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    _raise(f'query parameter {name} must be a boolean', code='invalid_query_parameter')


def get_query_list_of_str(request: web.Request, name: str, *, max_items: int = 64, item_max_len: int = 128) -> list[str]:
    values = _query_values(request, name)
    if len(values) > max_items:
        _raise(f'query parameter {name} exceeds max item count {max_items}', code='invalid_query_parameter')
    result: list[str] = []
    for idx, value in enumerate(values):
        result.append(_bounded_text(value, field=f'query parameter {name}[{idx}]', max_len=item_max_len))
    return result


def get_query_pagination(
    request: web.Request,
    *,
    default_limit: int = 100,
    max_limit: int = 500,
    default_offset: int = 0,
) -> dict[str, int]:
    limit = get_query_int(request, 'limit', default=default_limit, min_value=1, max_value=max_limit)
    offset = get_query_int(request, 'offset', default=default_offset, min_value=0)
    return {
        'limit': int(limit if limit is not None else default_limit),
        'offset': int(offset if offset is not None else default_offset),
    }


def get_route_identifier(request: web.Request, name: str, *, max_len: int = 128) -> str:
    value = request.match_info.get(name)
    if value is None:
        _raise(f'route parameter {name} is required', code='missing_route_parameter')
    if len(value) > max_len:
        _raise(f'route parameter {name} exceeds max length {max_len}', code='invalid_route_parameter')
    if any(ch not in _SAFE_IDENTIFIER_CHARS for ch in value):
        _raise(f'route parameter {name} contains invalid characters', code='invalid_route_parameter')
    return value


def get_url(payload: dict[str, Any], field: str, *, required: bool = False, allowed_schemes: Iterable[str] = ('http', 'https'), max_len: int = 2048) -> str | None:
    value = get_str(payload, field, required=required, max_len=max_len)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in set(allowed_schemes):
        _raise(f'{field} must use one of these schemes: {", ".join(allowed_schemes)}', code='invalid_url_scheme')
    if not parsed.netloc:
        _raise(f'{field} must include a network location', code='invalid_url')
    if parsed.username or parsed.password:
        _raise(f'{field} must not include embedded credentials', code='invalid_url')
    return value
