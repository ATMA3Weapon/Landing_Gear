"""Trustd_auth plugin: request-time auth middleware backed by Trustd.

Per the spec (section 15.3):
  - Handles token parsing, token verification callouts, principal extraction,
    request auth context injection, protected route helpers, and
    request-scope authorization checks.
  - Does NOT issue trust on its own — it enforces using Trustd-backed decisions.
  - Clearly separated from the broader trustd integration plugin.

This plugin registers an aiohttp middleware that:
  1. Parses the Bearer token from the Authorization header.
  2. Calls Trustd's token verification endpoint.
  3. Injects the resulting identity/principal into the request.
  4. Enforces route-level auth policies using the injected identity.

Config section: trustd_auth (falls back to trustd.base_url if not set)
  base_url      – Trustd base URL for token verification
  required      – if true, all routes without explicit allow_anonymous require auth
  timeout       – HTTP timeout seconds; default 5
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from .base import PluginBase

logger = logging.getLogger('landing_gear.plugins.trustd_auth')

PLUGIN_ID = 'trustd_auth'


class TrustdAuthPlugin(PluginBase):
    """Attach request auth middleware backed by Trustd.

    This plugin is kept strictly separate from TrustdPlugin so that
    request-time auth concerns do not bleed into general trust integration.
    """

    PLUGIN_ID = PLUGIN_ID
    DISPLAY_NAME = 'Trustd Auth Middleware'
    VERSION = '0.1.0'

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._base_url: str | None = None
        self._required: bool = False
        self._timeout: int = 5
        self._requests_verified: int = 0
        self._requests_rejected: int = 0
        self._session: Any = None

    async def startup(self, host_context: Any) -> None:
        import aiohttp
        self._base_url = self.config.get('base_url') or None
        self._required = bool(self.config.get('required', False))
        self._timeout = int(self.config.get('timeout', 5))
        self._session = aiohttp.ClientSession()

        # Fall back to trustd.base_url if not configured directly
        if not self._base_url and hasattr(host_context, 'config'):
            cfg = host_context.config or {}
            self._base_url = cfg.get('trustd', {}).get('base_url')

        if not self._base_url:
            logger.warning('trustd_auth plugin: base_url not configured — token verification will reject all tokens')

        if hasattr(host_context, 'set_component'):
            host_context.set_component(
                'trustd_auth_plugin',
                self,
                kind='service_runtime',
                role='auth_middleware',
                note='Trustd auth middleware plugin',
            )

        try:
            host_context.trustd_auth = self
        except (AttributeError, TypeError):
            pass

    async def shutdown(self, host_context: Any) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def register_middleware(self, app: web.Application) -> None:
        """Attach the Trustd-backed auth middleware to the aiohttp app.

        Must be called before the aiohttp app starts (i.e. before start_all),
        because aiohttp freezes the middleware list on startup.
        """
        app.middlewares.append(self._make_middleware())

    def _make_middleware(self):
        plugin = self

        @web.middleware
        async def trustd_auth_middleware(request: web.Request, handler):
            # Skip public endpoints
            route = request.match_info.route
            route_name = getattr(route, 'name', None)
            if route_name in {'landing_gear.healthz', 'landing_gear.readyz', 'landing_gear.status'}:
                return await handler(request)

            header = request.headers.get('Authorization', '')
            if not header:
                if plugin._required:
                    plugin._requests_rejected += 1
                    return web.json_response(
                        {'ok': False, 'error': 'authentication required', 'code': 'unauthorized'},
                        status=401,
                    )
                request['trustd_identity'] = None
                return await handler(request)

            if not header.startswith('Bearer '):
                plugin._requests_rejected += 1
                return web.json_response(
                    {'ok': False, 'error': 'unsupported authorization scheme', 'code': 'unauthorized'},
                    status=401,
                )

            token = header.removeprefix('Bearer ').strip()
            identity = await plugin._verify_token(token)

            if identity is None:
                plugin._requests_rejected += 1
                return web.json_response(
                    {'ok': False, 'error': 'invalid or expired token', 'code': 'unauthorized'},
                    status=401,
                )

            plugin._requests_verified += 1
            request['trustd_identity'] = identity
            return await handler(request)

        return trustd_auth_middleware

    async def _verify_token(self, token: str) -> dict[str, Any] | None:
        """Call Trustd's token verification endpoint.

        Returns the identity dict on success, None on failure.
        """
        if not self._base_url:
            return None
        try:
            import aiohttp
            url = self._base_url.rstrip('/') + '/api/v1/auth/verify'
            async with self._session.post(
                url,
                json={'token': token},
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status not in (200, 201):
                    return None
                data = await resp.json()
                if not isinstance(data, dict) or not data.get('ok'):
                    return None
                return data.get('identity') or data
        except Exception as exc:
            logger.warning('trustd_auth: token verification failed: %s', exc)
            return None

    def get_identity(self, request: Any) -> dict[str, Any] | None:
        """Extract the injected identity from a request, or None."""
        return request.get('trustd_identity')

    def require_identity(self, request: Any) -> dict[str, Any]:
        """Raise HTTP 401 if no identity is on the request."""
        identity = self.get_identity(request)
        if identity is None:
            raise web.HTTPUnauthorized(
                content_type='application/json',
                text='{"ok":false,"error":"authentication required","code":"unauthorized"}',
            )
        return identity

    def enrich_status(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            'base_url': self._base_url,
            'required': self._required,
            'requests_verified': self._requests_verified,
            'requests_rejected': self._requests_rejected,
        }
