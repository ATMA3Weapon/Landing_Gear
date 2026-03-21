from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from typing import Any, Literal

from .errors import ForbiddenError, UnauthorizedError


AuthMode = Literal["optional", "required"]


@dataclass(slots=True)
class Identity:
    subject: str
    scopes: set[str] = field(default_factory=set)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RouteAuth:
    mode: AuthMode = "optional"
    scope: str | None = None


class AuthProvider:
    async def authenticate_request(self, request: Any) -> Identity | None:
        return None


class StaticTokenAuthProvider(AuthProvider):
    def __init__(self, token_map: dict[str, dict[str, Any]]) -> None:
        self.token_map = token_map

    async def authenticate_request(self, request: Any) -> Identity | None:
        header = request.headers.get('Authorization', '')
        if not header:
            return None
        if not header.startswith('Bearer '):
            raise UnauthorizedError('unsupported authorization header')
        token = header.removeprefix('Bearer ').strip()
        record = self.token_map.get(token)
        if record is None:
            raise UnauthorizedError('invalid bearer token')
        return Identity(
            subject=record.get('subject', 'unknown'),
            scopes=set(record.get('scopes', [])),
            raw=record,
        )


class CompositeAuthProvider(AuthProvider):
    def __init__(self, providers: list[AuthProvider]) -> None:
        self.providers = providers

    async def authenticate_request(self, request: Any) -> Identity | None:
        for provider in self.providers:
            identity = await provider.authenticate_request(request)
            if identity is not None:
                return identity
        return None


def load_auth_provider(config: dict[str, Any], *, ctx: Any | None = None) -> AuthProvider | None:
    auth_config = config.get('auth', {}) or {}
    if not auth_config.get('enabled'):
        return None

    provider_path = auth_config.get('provider_path')
    static_tokens = auth_config.get('static_tokens', {}) or {}
    providers: list[AuthProvider] = []

    if provider_path:
        module_name, _, attr_name = str(provider_path).partition(':')
        if not module_name or not attr_name:
            raise ValueError('auth.provider_path must look like module.path:ProviderOrFactory')
        module = importlib.import_module(module_name)
        target = getattr(module, attr_name)
        provider = _build_auth_target(target, auth_config, ctx)
        providers.append(provider)

    if static_tokens:
        if not isinstance(static_tokens, dict):
            raise ValueError('auth.static_tokens must be a mapping')
        providers.append(StaticTokenAuthProvider(static_tokens))

    if not providers:
        return None
    if len(providers) == 1:
        return providers[0]
    return CompositeAuthProvider(providers)


def _build_auth_target(target: Any, auth_config: dict[str, Any], ctx: Any | None) -> AuthProvider:
    factory_config = dict(auth_config.get('provider_config', {}))
    if inspect.isclass(target):
        try:
            return target(factory_config, ctx=ctx)
        except TypeError:
            try:
                return target(factory_config)
            except TypeError:
                return target()
    result = target(factory_config, ctx=ctx)
    if inspect.isawaitable(result):
        raise TypeError('async auth provider factories are not supported')
    if not isinstance(result, AuthProvider):
        raise TypeError('configured auth provider factory did not return AuthProvider')
    return result


def optional_auth() -> RouteAuth:
    return RouteAuth(mode='optional')


def required_auth(scope: str | None = None) -> RouteAuth:
    return RouteAuth(mode='required', scope=scope)


def require_identity(identity: Identity | None) -> Identity:
    if identity is None:
        raise UnauthorizedError('authentication required')
    return identity


def require_scope(identity: Identity | None, scope: str) -> Identity:
    ident = require_identity(identity)
    if scope not in ident.scopes:
        raise ForbiddenError(f'missing required scope: {scope}')
    return ident


def enforce_route_auth(policy: RouteAuth, identity: Identity | None) -> Identity | None:
    if policy.mode == 'required':
        if policy.scope:
            return require_scope(identity, policy.scope)
        return require_identity(identity)
    if policy.scope:
        if identity is None:
            raise UnauthorizedError('authentication required')
        return require_scope(identity, policy.scope)
    return identity
