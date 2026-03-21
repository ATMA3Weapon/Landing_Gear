from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from .auth import optional_auth, required_auth

F = TypeVar('F', bound=Callable[..., Any])
Decorator = Callable[[F], F]


def route(method: str, path: str, *, tags: tuple[str, ...] = ()) -> Decorator:
    def decorator(func: F) -> F:
        setattr(func, '__lg_route__', {'method': method.upper(), 'path': path, 'tags': tuple(tags)})
        return func
    return decorator


def hook(name: str) -> Decorator:
    def decorator(func: F) -> F:
        setattr(func, '__lg_hook__', {'name': name})
        return func
    return decorator


def event_subscriber(name: str) -> Decorator:
    def decorator(func: F) -> F:
        setattr(func, '__lg_event__', {'name': name})
        return func
    return decorator


def public_call(name: str | None = None) -> Decorator:
    def decorator(func: F) -> F:
        setattr(func, '__lg_call__', {'name': name or func.__name__})
        return func
    return decorator


def health_check(name: str) -> Decorator:
    def decorator(func: F) -> F:
        setattr(func, '__lg_health__', {'name': name})
        return func
    return decorator


def startup_task(name: str | None = None) -> Decorator:
    def decorator(func: F) -> F:
        setattr(func, '__lg_startup_task__', {'name': name or func.__name__})
        return func
    return decorator


def shutdown_task(name: str | None = None) -> Decorator:
    def decorator(func: F) -> F:
        setattr(func, '__lg_shutdown_task__', {'name': name or func.__name__})
        return func
    return decorator


def auth(mode: str = 'required', scope: str | None = None) -> Decorator:
    def decorator(func: F) -> F:
        if mode == 'required':
            setattr(func, '__lg_auth__', required_auth(scope))
        elif mode == 'optional':
            setattr(func, '__lg_auth__', optional_auth())
        else:
            raise ValueError(f'unsupported auth mode: {mode}')
        return func
    return decorator


def requires_auth(scope: str | None = None) -> Decorator:
    return auth('required', scope=scope)


def allow_anonymous() -> Decorator:
    return auth('optional')
