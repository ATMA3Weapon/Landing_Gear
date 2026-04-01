from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any

from .auth import AuthProvider, Identity, RouteAuth, enforce_route_auth, optional_auth
from .errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError, ServiceError, UnauthorizedError
from .registry import (
    CallRegistry,
    HealthRegistry,
    HandlerRegistry,
    RepositoryRegistry,
    RouteRegistry,
    TaskRegistry,
)
from .requests import read_json
from .responses import (
    json_accepted,
    json_collection,
    json_created,
    json_error,
    json_no_content,
    json_operation,
    json_response,
)
from .tls import describe_tls_state
from .service_shape import build_service_shape
from .trustd_pki import NullTrustRegistrar, TrustRegistrar


class ServiceContext:
    def __init__(
        self,
        *,
        service_name: str,
        service_version: str,
        config: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
        auth_provider: AuthProvider | None = None,
        trust_registrar: TrustRegistrar | None = None,
    ) -> None:
        self.service_name = service_name
        self.service_version = service_version
        self.config = config or {}
        self.state = state or {}
        self.auth_provider = auth_provider
        self.trust_registrar = trust_registrar or NullTrustRegistrar()
        self.client_ssl_context = None

        self.routes = RouteRegistry()
        self.hooks = HandlerRegistry()
        self.events = HandlerRegistry()
        self.calls = CallRegistry()
        self.health = HealthRegistry()
        self.tasks = TaskRegistry()
        self.repositories = RepositoryRegistry()
        self.module_states: dict[str, dict[str, Any]] = {}
        self.loaded_modules: list[Any] = []
        self.managed_tasks: dict[str, asyncio.Task[Any]] = {}
        self.managed_task_owners: dict[str, str] = {}
        self._managed_task_errors: dict[str, str] = {}
        self.repository_owners: dict[str, str] = {}
        self.components: dict[str, Any] = {}
        self.component_owners: dict[str, str] = {}
        self.component_metadata: dict[str, dict[str, Any]] = {}
        self.task_registry_owners: dict[str, dict[str, str]] = {'startup': {}, 'shutdown': {}}
        self.call_owners: dict[str, str] = {}
        self.health_check_owners: dict[str, str] = {}
        self.hook_owners: dict[str, str] = {}
        self.event_owners: dict[str, str] = {}
        self.config_section_owners: dict[str, dict[str, Any]] = {}
        self.lifecycle_events: list[dict[str, Any]] = []



    def service_shape_model(self):
        return build_service_shape(self.config)

    def service_shape(self) -> dict[str, Any]:
        return self.service_shape_model().to_dict()

    def service_contract(self) -> dict[str, Any]:
        return self.service_shape_model().contract_summary()

    def runtime_views(self) -> dict[str, str]:
        return {
            'generic_service_runtime': '/status',
            'generic_service_health': '/healthz',
            'service_runtime': '/api/service/runtime',
            'service_domain_runtime': '/api/broker/runtime',
            'service_domain_diagnostics': '/api/diagnostics',
        }

    def service_runtime_surface(self) -> dict[str, Any]:
        return {
            'service': {
                'name': self.service_name,
                'version': self.service_version,
            },
            'service_shape': self.service_shape(),
            'service_contract': self.service_contract(),
            'runtime_views': self.runtime_views(),
            'components': self.component_snapshot(),
            'component_groups': self.component_groups(),
            'repositories': self.repository_snapshot(),
            'config_ownership': self.config_ownership_snapshot(),
            'lifecycle': self.lifecycle_snapshot(limit=15),
            'module_ownership': self.module_ownership_snapshot(),
        }


    def claim_config_section(self, path: str, *, owner: str | None = None, kind: str = 'service', note: str | None = None) -> None:
        path = str(path).strip()
        if not path:
            raise ValueError('config section path cannot be empty')
        entry = {
            'owner': owner or 'service',
            'kind': kind,
            'note': note,
            'exists': self.config_path_exists(path),
        }
        self.config_section_owners[path] = entry
        self.record_lifecycle_event('config_section.claimed', path=path, owner=entry['owner'], kind=kind)

    def _config_path_parts(self, path: str) -> list[str]:
        return [part for part in str(path).split('.') if part]

    def get_config_path_value(self, path: str, default: Any = None) -> Any:
        current: Any = self.config
        for part in self._config_path_parts(path):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def config_path_exists(self, path: str) -> bool:
        marker = object()
        return self.get_config_path_value(path, marker) is not marker

    def config_ownership_snapshot(self) -> dict[str, Any]:
        shape = self.service_shape_model()
        claims = {
            path: {
                **entry,
                'exists': self.config_path_exists(path),
                'value_type': type(self.get_config_path_value(path)).__name__ if self.config_path_exists(path) else None,
            }
            for path, entry in sorted(self.config_section_owners.items())
        }
        top_level_keys = sorted(self.config.keys()) if isinstance(self.config, dict) else []
        claimed_top_level = {path.split('.', 1)[0] for path in claims}
        kernel_sections = set(shape.kernel_config_sections)
        service_sections = set(shape.service_config_sections)
        unclaimed_top_level = [
            key for key in top_level_keys
            if key not in claimed_top_level and key not in kernel_sections and key not in service_sections
        ]
        return {
            'kernel_sections': {
                name: {'exists': self.config_path_exists(name), 'owner': 'landing_gear'}
                for name in shape.kernel_config_sections
            },
            'service_sections': {
                name: {'exists': self.config_path_exists(name), 'owner': 'service'}
                for name in shape.service_config_sections
            },
            'claims': claims,
            'unclaimed_top_level': unclaimed_top_level,
        }

    def record_lifecycle_event(self, event: str, **fields: Any) -> None:
        entry = {
            'event': event,
            'at': datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        self.lifecycle_events.append(entry)
        if len(self.lifecycle_events) > 200:
            del self.lifecycle_events[:-200]

    def lifecycle_snapshot(self, *, limit: int = 25) -> dict[str, Any]:
        return {
            'recent_events': self.lifecycle_events[-limit:],
            'module_phase_counts': self.module_phase_counts(),
            'managed_tasks': self.managed_task_status(),
            'config_sections': self.config_ownership_snapshot(),
        }

    def lifecycle_contract(self) -> dict[str, Any]:
        return {
            'setup_phase_expectations': [
                'create module-owned repositories',
                'read validated config and prepare internal state',
                'do not start managed background tasks yet',
            ],
            'register_phase_expectations': [
                'register routes, hooks, calls, and startup/shutdown tasks',
                'bind service surface to already-prepared state',
            ],
            'start_phase_expectations': [
                'start managed background tasks and long-lived loops',
                'assume registration is complete before background work begins',
            ],
            'stop_phase_expectations': [
                'stop module-owned behavior cleanly',
                'allow the kernel to cancel remaining managed tasks during shutdown',
            ],
        }

    def module_phase_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for state in self.module_states.values():
            phase = str(state.get('phase') or 'unknown')
            counts[phase] = counts.get(phase, 0) + 1
        return counts

    def module_runtime_snapshot(self) -> dict[str, Any]:
        return {
            'modules': self.module_states,
            'repositories': self.repository_snapshot(),
            'components': self.component_snapshot(),
            'task_registrations': self.registered_task_snapshot(),
            'managed_tasks': self.managed_task_status(),
            'config_sections': self.config_ownership_snapshot(),
            'counts': {
                'core': len([m for m in self.module_states.values() if m.get('kind') == 'core']),
                'plugin': len([m for m in self.module_states.values() if m.get('kind') == 'plugin']),
                'total': len(self.module_states),
            },
            'phase_counts': self.module_phase_counts(),
            'ownership': self.module_ownership_snapshot(),
        }


    def config_profile(self) -> dict[str, Any]:
        auth_config = self.get_section('auth') if isinstance(self.config, dict) else {}
        tls = self.tls_state()
        service = self.get_section('service') if isinstance(self.config, dict) else {}
        core_modules = self.get_section('core_modules') if isinstance(self.config, dict) else {}
        plugins = self.get_section('plugins') if isinstance(self.config, dict) else {}
        enabled_core = sorted([name for name, section in core_modules.items() if isinstance(section, dict) and section.get('enabled', True) is not False])
        enabled_plugins = sorted([name for name, section in plugins.items() if isinstance(section, dict) and section.get('enabled', True) is not False])
        hub_config = self.get_section('hub') if isinstance(self.config, dict) and isinstance(self.config.get('hub', {}), dict) else {}
        storage = hub_config.get('storage', {}) if isinstance(hub_config.get('storage', {}), dict) else {}
        return {
            'service_name': self.service_name,
            'service_version': self.service_version,
            'package_root': service.get('package_root', self.service_name),
            'auth_enabled': bool(auth_config.get('enabled', False)),
            'auth_mode': 'custom_provider' if auth_config.get('provider_path') else ('static_tokens' if auth_config.get('static_tokens') else 'disabled'),
            'tls_enabled': bool(tls['inbound']['enabled']),
            'outbound_tls_enabled': bool(tls['outbound']['enabled']),
            'core_modules_enabled': enabled_core,
            'plugins_enabled': enabled_plugins,
            'storage_backend': str(storage.get('backend', 'memory')),
            'env_overrides': list(self.state.get('env_overrides', [])),
        }

    def readiness_snapshot(self) -> dict[str, Any]:
        blueprint_missing = []
        config_path = self.state.get('config_path')
        if not config_path:
            blueprint_missing.append('config_path')
        auth_enabled = bool(self.config.get('auth', {}).get('enabled', False)) if isinstance(self.config.get('auth', {}), dict) else False
        ready_checks = {
            'service_shape_declared': bool(self.service_shape().get('package_root')),
            'modules_loaded': bool(self.loaded_modules),
            'routes_registered': bool(self.routes.routes),
            'repositories_present': bool(self.list_repositories()),
            'components_present': bool(self.list_components()),
            'auth_configured': auth_enabled,
        }
        warnings: list[str] = []
        if not auth_enabled:
            warnings.append('auth is disabled')
        if not self.list_repositories():
            warnings.append('no repositories are registered yet')
        if not self.routes.routes:
            warnings.append('no routes are registered yet')
        return {
            'checks': ready_checks,
            'ready': all(ready_checks.values()),
            'warnings': warnings,
            'env_overrides': list(self.state.get('env_overrides', [])),
            'config_path': config_path,
        }

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def get_section(self, key: str) -> dict[str, Any]:
        value = self.config.get(key, {})
        if not isinstance(value, dict):
            raise TypeError(f'config section is not a mapping: {key}')
        return value

    def logger(self, name: str | None = None) -> logging.Logger:
        return logging.getLogger(name or self.service_name)

    def correlation_id(self, request: Any | None = None) -> str | None:
        if request is None:
            return None
        return request.get('correlation_id')

    def register_route(
        self,
        method: str,
        path: str,
        handler,
        *,
        owner: str | None = None,
        auth: RouteAuth | None = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        self.routes.add(
            method,
            path,
            handler,
            owner=owner,
            auth=auth,
            tags=tags,
        )

    def register_hook(self, name: str, handler, *, owner: str | None = None) -> None:
        self.hooks.add(name, handler)
        self.hook_owners[name] = owner or 'service'
        self.record_lifecycle_event('hook.registered', hook_name=name, owner=owner or 'service')

    def subscribe_event(self, name: str, handler, *, owner: str | None = None) -> None:
        self.events.add(name, handler)
        self.event_owners[name] = owner or 'service'
        self.record_lifecycle_event('event.registered', event_name=name, owner=owner or 'service')

    def register_call(self, name: str, handler, *, owner: str | None = None) -> None:
        self.calls.add(name, handler)
        self.call_owners[name] = owner or 'service'
        self.record_lifecycle_event('call.registered', call_name=name, owner=owner or 'service')

    def register_health_check(self, name: str, handler, *, owner: str | None = None) -> None:
        self.health.add(name, handler)
        self.health_check_owners[name] = owner or 'service'
        self.record_lifecycle_event('health_check.registered', health_check=name, owner=owner or 'service')

    def register_startup_task(self, name: str, handler, *, owner: str | None = None) -> None:
        self.tasks.add_startup(name, handler)
        self.task_registry_owners['startup'][name] = owner or 'service'
        self.record_lifecycle_event('startup_task.registered', task_name=name, owner=owner or 'service')

    def register_shutdown_task(self, name: str, handler, *, owner: str | None = None) -> None:
        self.tasks.add_shutdown(name, handler)
        self.task_registry_owners['shutdown'][name] = owner or 'service'
        self.record_lifecycle_event('shutdown_task.registered', task_name=name, owner=owner or 'service')

    async def emit_hook(self, name: str, **kwargs: Any) -> list[Any]:
        return await self.hooks.emit(name, **kwargs)

    async def emit_event(self, name: str, **kwargs: Any) -> list[Any]:
        return await self.events.emit(name, **kwargs)

    async def call(self, name: str, **kwargs: Any) -> Any:
        return await self.calls.invoke(name, **kwargs)

    async def read_json(self, request, *, max_bytes: int = 1024 * 1024) -> dict[str, Any]:
        return await read_json(request, max_bytes=max_bytes)

    def require_fields(self, payload: dict[str, Any], *field_names: str) -> None:
        from .requests import require_fields
        require_fields(payload, *field_names)

    def reject_unknown_fields(self, payload: dict[str, Any], *, allowed: list[str] | tuple[str, ...] | set[str]) -> None:
        from .requests import reject_unknown_fields
        reject_unknown_fields(payload, allowed=allowed)

    def get_identifier(self, payload: dict[str, Any], field: str, **kwargs: Any) -> str | None:
        from .requests import get_identifier
        return get_identifier(payload, field, **kwargs)

    def ensure_identifier_value(self, value: str, *, field: str = "value", max_len: int = 128):
        from .requests import ensure_identifier_value
        return ensure_identifier_value(value, field=field, max_len=max_len)

    def get_str_field(self, payload: dict[str, Any], field: str, **kwargs: Any) -> str | None:
        from .requests import get_str
        return get_str(payload, field, **kwargs)

    def get_enum_field(self, payload: dict[str, Any], field: str, **kwargs: Any) -> str | None:
        from .requests import get_enum
        return get_enum(payload, field, **kwargs)

    def get_mapping_field(self, payload: dict[str, Any], field: str, **kwargs: Any) -> dict[str, Any]:
        from .requests import get_mapping
        return get_mapping(payload, field, **kwargs)

    def get_list_of_str_field(self, payload: dict[str, Any], field: str, **kwargs: Any) -> list[str]:
        from .requests import get_list_of_str
        return get_list_of_str(payload, field, **kwargs)

    def get_route_identifier(self, request: Any, name: str, *, max_len: int = 128) -> str:
        from .requests import get_route_identifier
        return get_route_identifier(request, name, max_len=max_len)

    def get_query_str(self, request: Any, name: str, **kwargs: Any) -> str | None:
        from .requests import get_query_str
        return get_query_str(request, name, **kwargs)

    def get_query_int(self, request: Any, name: str, **kwargs: Any) -> int | None:
        from .requests import get_query_int
        return get_query_int(request, name, **kwargs)

    def get_query_bool(self, request: Any, name: str, **kwargs: Any) -> bool | None:
        from .requests import get_query_bool
        return get_query_bool(request, name, **kwargs)

    def get_query_list_of_str(self, request: Any, name: str, **kwargs: Any) -> list[str]:
        from .requests import get_query_list_of_str
        return get_query_list_of_str(request, name, **kwargs)

    def get_query_pagination(self, request: Any, **kwargs: Any) -> dict[str, int]:
        from .requests import get_query_pagination
        return get_query_pagination(request, **kwargs)

    def get_url_field(self, payload: dict[str, Any], field: str, **kwargs: Any) -> str | None:
        from .requests import get_url
        return get_url(payload, field, **kwargs)

    def json_response(self, data: Any, *, status: int = 200, meta: dict[str, Any] | None = None, request: Any | None = None):
        return json_response(data, status=status, meta=meta, correlation_id=self.correlation_id(request))

    def json_created(self, data: Any, *, meta: dict[str, Any] | None = None, request: Any | None = None):
        return json_created(data, meta=meta, correlation_id=self.correlation_id(request))

    def json_accepted(self, data: Any, *, meta: dict[str, Any] | None = None, request: Any | None = None):
        return json_accepted(data, meta=meta, correlation_id=self.correlation_id(request))

    def json_collection(
        self,
        items: list[Any],
        *,
        item_name: str = 'items',
        total: int | None = None,
        meta: dict[str, Any] | None = None,
        request: Any | None = None,
        status: int = 200,
        limit: int | None = None,
        offset: int | None = None,
    ):
        return json_collection(
            items,
            item_name=item_name,
            total=total,
            meta=meta,
            correlation_id=self.correlation_id(request),
            status=status,
            limit=limit,
            offset=offset,
        )


    def json_operation(
        self,
        operation: str,
        *,
        status_text: str = 'ok',
        data: Any = None,
        meta: dict[str, Any] | None = None,
        request: Any | None = None,
        status: int = 200,
    ):
        return json_operation(
            operation,
            status_text=status_text,
            result=data,
            meta=meta,
            correlation_id=self.correlation_id(request),
            status=status,
        )

    def json_no_content(self):
        return json_no_content()

    def json_error(
        self,
        message: str,
        *,
        status: int = 400,
        code: str | None = None,
        details: Any = None,
        meta: dict[str, Any] | None = None,
        request: Any | None = None,
    ):
        return json_error(
            message,
            status=status,
            code=code,
            details=details,
            meta=meta,
            correlation_id=self.correlation_id(request),
        )

    def bad_request(self, message: str, *, code: str = 'bad_request', details: object | None = None) -> None:
        raise BadRequestError(message, code=code, details=details)

    def unauthorized(self, message: str = 'unauthorized', *, code: str = 'unauthorized') -> None:
        raise UnauthorizedError(message=message, code=code)

    def forbidden(self, message: str = 'forbidden', *, code: str = 'forbidden') -> None:
        raise ForbiddenError(message=message, code=code)

    def not_found(self, message: str = 'not found', *, code: str = 'not_found') -> None:
        raise NotFoundError(message=message, code=code)

    def conflict(self, message: str, *, code: str = 'conflict', details: object | None = None) -> None:
        raise ConflictError(message=message, code=code, details=details)

    def service_error(self, message: str, *, status: int = 500, code: str = 'service_error', details: object | None = None) -> None:
        raise ServiceError(message=message, status=status, code=code, details=details)

    def get_repository(self, name: str) -> Any:
        registry = getattr(self.repositories, 'repositories', None)
        if isinstance(registry, dict):
            return registry.get(name)
        return self.repositories.get(name)

    def set_repository(self, name: str, repo: Any, *, owner: str | None = None) -> None:
        self.repositories.add(name, repo)
        self.repository_owners[name] = owner or 'service'
        self.record_lifecycle_event('repository.registered', repository=name, owner=owner or 'service')

    def list_repositories(self) -> list[str]:
        return self.repositories.list_names()

    def set_component(
        self,
        name: str,
        value: Any,
        *,
        owner: str | None = None,
        kind: str = 'service_component',
        role: str | None = None,
        note: str | None = None,
    ) -> None:
        self.components[name] = value
        component_owner = owner or 'service'
        self.component_owners[name] = component_owner
        self.component_metadata[name] = {
            'kind': kind,
            'role': role,
            'note': note,
        }
        self.record_lifecycle_event(
            'component.registered',
            component=name,
            owner=component_owner,
            kind=kind,
            role=role,
        )

    def get_component(self, name: str, default: Any = None) -> Any:
        return self.components.get(name, default)

    def list_components(self) -> list[str]:
        return sorted(self.components.keys())

    def component_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for name, value in sorted(self.components.items()):
            metadata = dict(self.component_metadata.get(name, {}))
            summary = None
            if hasattr(value, 'summary') and callable(getattr(value, 'summary')):
                try:
                    summary = value.summary()
                except Exception as exc:  # pragma: no cover - defensive visibility only
                    summary = {'error': str(exc)}
            snapshot[name] = {
                'owner': self.component_owners.get(name, 'service'),
                'type': type(value).__name__,
                'kind': metadata.get('kind', 'service_component'),
                'role': metadata.get('role'),
                'note': metadata.get('note'),
                'summary': summary,
            }
        return snapshot

    def component_groups(self) -> dict[str, list[str]]:
        groups = {
            'service_runtime': [],
            'service_domain': [],
            'service_component': [],
            'other': [],
        }
        for name, details in self.component_snapshot().items():
            kind = details.get('kind') or 'other'
            if kind in groups:
                groups[kind].append(name)
            else:
                groups['other'].append(name)
        return {key: sorted(value) for key, value in groups.items() if value}

    async def repository_health(self) -> dict[str, Any]:
        return await self.repositories.health()

    async def authenticate_request(self, request: Any) -> Identity | None:
        if self.auth_provider is None:
            request['identity'] = None
            return None
        identity = await self.auth_provider.authenticate_request(request)
        request['identity'] = identity
        return identity

    def enforce_route_auth(self, request: Any, policy: RouteAuth) -> Identity | None:
        identity = request.get('identity')
        return enforce_route_auth(policy, identity)

    def set_client_ssl_context(self, ssl_context: Any) -> None:
        self.client_ssl_context = ssl_context

    def tls_state(self) -> dict[str, Any]:
        return describe_tls_state(self.config)

    def start_managed_task(self, name: str, coro: Any, *, owner: str | None = None) -> asyncio.Task[Any]:
        if name in self.managed_tasks and not self.managed_tasks[name].done():
            raise ValueError(f'managed task already running: {name}')
        task_owner = owner or 'service'
        owner_state = self.module_states.get(task_owner, {}) if owner and owner != 'service' else {}
        owner_phase = str(owner_state.get('phase') or '') if owner_state else ''
        if owner and owner != 'service' and owner_phase not in {'registered', 'started'}:
            phase_name = owner_phase or 'unknown'
            raise ValueError(f'module {owner} cannot start managed task from phase {phase_name}')
        self.record_lifecycle_event('managed_task.starting', task_name=name, owner=task_owner)
        task = asyncio.create_task(coro, name=name)
        self.managed_tasks[name] = task
        self.managed_task_owners[name] = task_owner

        def _done_callback(done_task: asyncio.Task[Any]) -> None:
            try:
                done_task.result()
                self._managed_task_errors.pop(name, None)
                self.record_lifecycle_event('managed_task.completed', task_name=name, owner=task_owner)
            except asyncio.CancelledError:
                self._managed_task_errors.pop(name, None)
                self.record_lifecycle_event('managed_task.cancelled', task_name=name, owner=task_owner)
            except Exception as exc:
                self._managed_task_errors[name] = str(exc)
                self.record_lifecycle_event('managed_task.failed', task_name=name, owner=task_owner, error=str(exc))
                self.logger().exception('managed task failed: %s', name)

        task.add_done_callback(_done_callback)
        return task

    async def stop_managed_tasks(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, task in list(self.managed_tasks.items()):
            if task.done():
                error = self._managed_task_errors.get(name)
                results[name] = {'ok': error is None, 'error': error}
                continue
            task.cancel()
            try:
                await task
                results[name] = {'ok': True, 'cancelled': True}
            except asyncio.CancelledError:
                results[name] = {'ok': True, 'cancelled': True}
            except Exception as exc:
                results[name] = {'ok': False, 'error': str(exc)}
        return results

    def managed_task_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {}
        for name, task in self.managed_tasks.items():
            error = self._managed_task_errors.get(name)
            status[name] = {
                'owner': self.managed_task_owners.get(name, 'service'),
                'done': task.done(),
                'cancelled': task.cancelled(),
                'error': error,
            }
        return status

    def repository_snapshot(self) -> dict[str, Any]:
        return {
            name: {
                'owner': self.repository_owners.get(name, 'service'),
                'type': type(self.get_repository(name)).__name__,
            }
            for name in self.list_repositories()
        }

    def registered_task_snapshot(self) -> dict[str, Any]:
        return {
            'startup': dict(sorted(self.task_registry_owners['startup'].items())),
            'shutdown': dict(sorted(self.task_registry_owners['shutdown'].items())),
        }

    def registry_ownership_snapshot(self) -> dict[str, Any]:
        return {
            'routes': {f"{route.method} {route.path}": route.owner or 'service' for route in self.routes.routes},
            'calls': dict(sorted(self.call_owners.items())),
            'health_checks': dict(sorted(self.health_check_owners.items())),
            'hooks': dict(sorted(self.hook_owners.items())),
            'events': dict(sorted(self.event_owners.items())),
            'tasks': self.registered_task_snapshot(),
        }

    def module_ownership_snapshot(self) -> dict[str, Any]:
        route_owners: dict[str, list[str]] = {}
        for route in self.routes.routes:
            owner = route.owner or 'service'
            route_owners.setdefault(owner, []).append(f"{route.method} {route.path}")
        for values in route_owners.values():
            values.sort()

        module_ids = sorted(set(self.module_states.keys()) | set(self.repository_owners.values()) | set(self.component_owners.values()) | set(self.managed_task_owners.values()) | set(self.call_owners.values()) | set(self.health_check_owners.values()) | set(self.hook_owners.values()) | set(self.event_owners.values()) | set(self.task_registry_owners['startup'].values()) | set(self.task_registry_owners['shutdown'].values()))
        modules: dict[str, Any] = {}
        warnings: list[str] = []
        for module_id in module_ids:
            if module_id == 'service':
                continue
            state = self.module_states.get(module_id, {})
            modules[module_id] = {
                'phase': state.get('phase'),
                'kind': state.get('kind'),
                'repositories': sorted([name for name, owner in self.repository_owners.items() if owner == module_id]),
                'components': sorted([name for name, owner in self.component_owners.items() if owner == module_id]),
                'managed_tasks': sorted([name for name, owner in self.managed_task_owners.items() if owner == module_id]),
                'routes': route_owners.get(module_id, []),
                'calls': sorted([name for name, owner in self.call_owners.items() if owner == module_id]),
                'health_checks': sorted([name for name, owner in self.health_check_owners.items() if owner == module_id]),
                'hooks': sorted([name for name, owner in self.hook_owners.items() if owner == module_id]),
                'events': sorted([name for name, owner in self.event_owners.items() if owner == module_id]),
                'startup_tasks': sorted([name for name, owner in self.task_registry_owners['startup'].items() if owner == module_id]),
                'shutdown_tasks': sorted([name for name, owner in self.task_registry_owners['shutdown'].items() if owner == module_id]),
                'config_sections': sorted([path for path, entry in self.config_section_owners.items() if entry.get('owner') == module_id]),
            }
            surface_count = sum(len(modules[module_id][key]) for key in ('repositories','components','managed_tasks','routes','calls','health_checks','hooks','events','startup_tasks','shutdown_tasks','config_sections'))
            modules[module_id]['surface_count'] = surface_count
            if module_id in self.module_states and surface_count == 0:
                warnings.append(f'module {module_id} is loaded but does not own any registered surface')

        return {
            'modules': modules,
            'registry_ownership': self.registry_ownership_snapshot(),
            'warnings': warnings,
        }

    def auto_register(self, instance: Any) -> None:
        owner = getattr(instance.INFO, 'id', instance.__class__.__name__)
        for _name, member in inspect.getmembers(instance, predicate=callable):
            route_def = getattr(member, '__lg_route__', None)
            if route_def is not None:
                auth_policy = getattr(member, '__lg_auth__', None) or optional_auth()
                self.register_route(
                    route_def['method'],
                    route_def['path'],
                    member,
                    owner=owner,
                    auth=auth_policy,
                    tags=tuple(route_def.get('tags', ())),
                )

            hook_def = getattr(member, '__lg_hook__', None)
            if hook_def is not None:
                self.register_hook(hook_def['name'], member, owner=owner)

            event_def = getattr(member, '__lg_event__', None)
            if event_def is not None:
                self.subscribe_event(event_def['name'], member, owner=owner)

            call_def = getattr(member, '__lg_call__', None)
            if call_def is not None:
                self.register_call(call_def['name'], member, owner=owner)

            health_def = getattr(member, '__lg_health__', None)
            if health_def is not None:
                self.register_health_check(health_def['name'], member, owner=owner)

            startup_def = getattr(member, '__lg_startup_task__', None)
            if startup_def is not None:
                self.register_startup_task(startup_def['name'], member, owner=owner)

            shutdown_def = getattr(member, '__lg_shutdown_task__', None)
            if shutdown_def is not None:
                self.register_shutdown_task(shutdown_def['name'], member, owner=owner)

    def record_module_state(self, module_id: str, **fields: Any) -> None:
        state = self.module_states.setdefault(module_id, {})
        state.update(fields)
        state.setdefault('module_id', module_id)
        state.setdefault('owned_repositories', [])
        state.setdefault('managed_tasks', [])
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        state['owned_repositories'] = sorted([name for name, owner in self.repository_owners.items() if owner == module_id])
        state['owned_components'] = sorted([name for name, owner in self.component_owners.items() if owner == module_id])
        state['managed_tasks'] = sorted([name for name, owner in self.managed_task_owners.items() if owner == module_id])
