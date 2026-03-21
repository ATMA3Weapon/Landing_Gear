from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .auth import RouteAuth, optional_auth
from .errors import ConflictError, NotFoundError


@dataclass(slots=True)
class RouteDef:
    method: str
    path: str
    handler: Callable[..., Any]
    owner: str | None = None
    auth: RouteAuth = field(default_factory=optional_auth)
    tags: tuple[str, ...] = ()


@dataclass(slots=True)
class RouteRegistry:
    routes: list[RouteDef] = field(default_factory=list)

    def add(
        self,
        method: str,
        path: str,
        handler: Callable[..., Any],
        *,
        owner: str | None = None,
        auth: RouteAuth | None = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        normalized_method = method.upper()
        for existing in self.routes:
            if existing.method == normalized_method and existing.path == path:
                raise ConflictError(
                    f'route already registered: {normalized_method} {path}',
                    code='route_already_registered',
                )
        self.routes.append(
            RouteDef(
                method=normalized_method,
                path=path,
                handler=handler,
                owner=owner,
                auth=auth or optional_auth(),
                tags=tuple(tags),
            )
        )


@dataclass(slots=True)
class HandlerRegistry:
    handlers: dict[str, list[Callable[..., Awaitable[Any]]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add(self, name: str, handler: Callable[..., Awaitable[Any]]) -> None:
        self.handlers[name].append(handler)

    async def emit(self, name: str, **kwargs: Any) -> list[Any]:
        results: list[Any] = []
        for handler in self.handlers.get(name, []):
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            results.append(result)
        return results


@dataclass(slots=True)
class CallRegistry:
    calls: dict[str, Callable[..., Awaitable[Any]]] = field(default_factory=dict)

    def add(self, name: str, handler: Callable[..., Awaitable[Any]]) -> None:
        if name in self.calls:
            raise ConflictError(f'call already registered: {name}', code='call_already_registered')
        self.calls[name] = handler

    async def invoke(self, name: str, **kwargs: Any) -> Any:
        handler = self.calls.get(name)
        if handler is None:
            raise NotFoundError(f'call not registered: {name}', code='call_not_registered')
        result = handler(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


@dataclass(slots=True)
class HealthRegistry:
    checks: dict[str, Callable[..., Awaitable[Any]]] = field(default_factory=dict)

    def add(self, name: str, handler: Callable[..., Awaitable[Any]]) -> None:
        if name in self.checks:
            raise ConflictError(
                f'health check already registered: {name}',
                code='health_check_already_registered',
            )
        self.checks[name] = handler

    async def run_all(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, handler in self.checks.items():
            try:
                result = handler()
                if inspect.isawaitable(result):
                    result = await result
                results[name] = result
            except Exception as exc:
                results[name] = {'ok': False, 'error': str(exc)}
        return results


@dataclass(slots=True)
class TaskRegistry:
    startup: dict[str, Callable[..., Awaitable[Any]]] = field(default_factory=dict)
    shutdown: dict[str, Callable[..., Awaitable[Any]]] = field(default_factory=dict)

    def add_startup(self, name: str, handler: Callable[..., Awaitable[Any]]) -> None:
        if name in self.startup:
            raise ConflictError(
                f'startup task already registered: {name}',
                code='startup_task_already_registered',
            )
        self.startup[name] = handler

    def add_shutdown(self, name: str, handler: Callable[..., Awaitable[Any]]) -> None:
        if name in self.shutdown:
            raise ConflictError(
                f'shutdown task already registered: {name}',
                code='shutdown_task_already_registered',
            )
        self.shutdown[name] = handler

    async def _run(self, tasks: dict[str, Callable[..., Awaitable[Any]]]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, handler in tasks.items():
            try:
                result = handler()
                if inspect.isawaitable(result):
                    result = await result
                results[name] = {'ok': True, 'result': result}
            except Exception as exc:
                results[name] = {'ok': False, 'error': str(exc)}
        return results

    async def run_startup(self) -> dict[str, Any]:
        return await self._run(self.startup)

    async def run_shutdown(self) -> dict[str, Any]:
        return await self._run(self.shutdown)


@dataclass(slots=True)
class RepositoryRegistry:
    repositories: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, repo: Any) -> None:
        if name in self.repositories:
            raise ConflictError(
                f'repository already registered: {name}',
                code='repository_already_registered',
            )
        self.repositories[name] = repo

    def get(self, name: str) -> Any:
        if name not in self.repositories:
            raise NotFoundError(f'repository not registered: {name}', code='repository_not_registered')
        return self.repositories[name]

    def list_names(self) -> list[str]:
        return sorted(self.repositories.keys())

    async def health(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, repo in self.repositories.items():
            health = getattr(repo, 'health', None)
            if health is None:
                results[name] = {'ok': True, 'backend': repo.__class__.__name__}
                continue
            try:
                result = health()
                if inspect.isawaitable(result):
                    result = await result
                results[name] = result
            except Exception as exc:
                results[name] = {'ok': False, 'error': str(exc)}
        return results
