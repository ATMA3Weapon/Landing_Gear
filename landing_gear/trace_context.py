"""Trace context helpers: request_id and correlation_id propagation.

Per the Landing Gear spec, all services must propagate trace fields for
requests and cross-service operations. This module provides the canonical
helpers for generating and reading those fields.
"""
from __future__ import annotations

import uuid
from typing import Any


CORRELATION_HEADER = 'X-Correlation-ID'
REQUEST_ID_HEADER = 'X-Request-ID'


def new_request_id() -> str:
    """Generate a new unique request ID."""
    return str(uuid.uuid4())


def new_correlation_id() -> str:
    """Generate a new unique correlation ID."""
    return str(uuid.uuid4())


def extract_or_generate(request: Any) -> tuple[str, str]:
    """Extract correlation_id and request_id from a request, generating if absent.

    Returns (correlation_id, request_id). Both may be the same value when only
    one inbound header is present.
    """
    correlation_id = (
        request.headers.get(CORRELATION_HEADER)
        or request.headers.get(REQUEST_ID_HEADER)
        or new_correlation_id()
    )
    request_id = request.headers.get(REQUEST_ID_HEADER) or correlation_id
    return correlation_id, request_id


def get_correlation_id(request: Any) -> str | None:
    """Read the correlation_id already attached to a request object."""
    return request.get('correlation_id')


def get_request_id(request: Any) -> str | None:
    """Read the request_id already attached to a request object."""
    return request.get('request_id')


def make_trace_meta(request: Any | None) -> dict[str, str]:
    """Return a meta dict with correlation_id for use in response envelopes."""
    if request is None:
        return {}
    cid = get_correlation_id(request)
    return {'correlation_id': cid} if cid else {}
