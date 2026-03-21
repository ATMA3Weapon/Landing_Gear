from __future__ import annotations

import logging

from aiohttp import web

from .errors import ServiceError
from .logging import correlation_middleware, request_logging_middleware
from .responses import json_error


LANDING_GEAR_CTX_KEY = web.AppKey('landing_gear_ctx', object)
LANDING_GEAR_SERVER_SSL_CONTEXT_KEY = web.AppKey('landing_gear_server_ssl_context', object)
LANDING_GEAR_CLIENT_SSL_CONTEXT_KEY = web.AppKey('landing_gear_client_ssl_context', object)


def _correlation_meta(request: web.Request) -> dict[str, str]:
    correlation_id = request.get('correlation_id')
    return {'correlation_id': correlation_id} if correlation_id else {}


@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except ServiceError as exc:
        return json_error(
            exc.message,
            status=exc.status,
            code=exc.code,
            details=exc.details,
            meta=_correlation_meta(request),
        )
    except web.HTTPException:
        raise
    except ValueError as exc:
        return json_error(
            str(exc),
            status=400,
            code='value_error',
            meta=_correlation_meta(request),
        )
    except Exception:
        logging.getLogger('landing_gear.errors').exception('unhandled request error for %s %s', request.method, request.path)
        return json_error(
            'internal error',
            status=500,
            code='internal_error',
            meta=_correlation_meta(request),
        )


@web.middleware
async def auth_middleware(request: web.Request, handler):
    route = request.match_info.route
    path = request.path
    if getattr(route, 'name', None) in {'landing_gear.healthz', 'landing_gear.status'} or path in {'/healthz', '/status'}:
        return await handler(request)
    ctx = request.app[LANDING_GEAR_CTX_KEY]
    await ctx.authenticate_request(request)
    return await handler(request)


class KernelApp:
    def __init__(self, ctx, module_manager=None) -> None:
        self.ctx = ctx
        self.module_manager = module_manager
        self.web_app = web.Application(
            middlewares=[error_middleware, correlation_middleware, request_logging_middleware, auth_middleware]
        )
        self.web_app[LANDING_GEAR_CTX_KEY] = ctx
        self.web_app.on_cleanup.append(self._on_cleanup)

    def bind_routes(self) -> None:
        for route in self.ctx.routes.routes:
            self.web_app.router.add_route(route.method, route.path, self._wrap_route(route))

    def _wrap_route(self, route):
        async def wrapped(request: web.Request):
            self.ctx.enforce_route_auth(request, route.auth)
            response = await route.handler(request)
            response.headers['X-Landing-Gear-Service'] = self.ctx.service_name
            correlation_id = request.get('correlation_id')
            if correlation_id:
                response.headers['X-Correlation-ID'] = correlation_id
                response.headers['X-Request-ID'] = correlation_id
            return response

        return wrapped

    def add_builtin_status_routes(self) -> None:
        async def healthz(request: web.Request):
            checks = await self.ctx.health.run_all()
            repo_health = await self.ctx.repository_health()
            module_health = {}
            if self.module_manager is not None:
                module_health = await self.module_manager.collect_health()
            ok = all(bool(v.get('ok', False)) for v in checks.values()) and all(
                bool(v.get('ok', False)) for v in module_health.values()
            ) and all(bool(v.get('ok', False)) for v in repo_health.values())
            return self.ctx.json_response(
                {
                    'ok': ok,
                    'checks': checks,
                    'repositories': repo_health,
                    'modules': module_health,
                    'managed_tasks': self.ctx.managed_task_status(),
                },
                request=request,
            )

        async def status(request: web.Request):
            return self.ctx.json_response(
                {
                    'service': self.ctx.service_name,
                    'version': self.ctx.service_version,
                    'service_shape': {
                        **self.ctx.service_shape(),
                        'routes_bound': len(self.ctx.routes.routes),
                        'core_modules_loaded': len([m for m in self.ctx.module_states.values() if m.get('kind') == 'core']),
                        'plugins_loaded': len([m for m in self.ctx.module_states.values() if m.get('kind') == 'plugin']),
                    },
                    'service_contract': self.ctx.service_contract(),
                    'lifecycle_contract': self.ctx.lifecycle_contract(),
                    'config_profile': self.ctx.config_profile(),
                    'readiness': self.ctx.readiness_snapshot(),
                    'routes': [
                        {
                            'method': route.method,
                            'path': route.path,
                            'owner': route.owner,
                            'auth_mode': route.auth.mode,
                            'required_scope': route.auth.scope,
                            'tags': list(route.tags),
                        }
                        for route in self.ctx.routes.routes
                    ],
                    'calls': sorted(self.ctx.calls.calls.keys()),
                    'repositories': self.ctx.list_repositories(),
                    'components': self.ctx.list_components(),
                    'component_groups': self.ctx.component_groups(),
                    'tls': self.ctx.tls_state(),
                    'modules': self.ctx.module_runtime_snapshot(),
                    'service_components': self.ctx.component_snapshot(),
                    'service_views': self.ctx.runtime_views(),
                    'lifecycle': self.ctx.lifecycle_snapshot(),
                    'startup_results': self.ctx.state.get('startup_results', {}),
                    'shutdown_results': self.ctx.state.get('shutdown_results', {}),
                    'managed_tasks': self.ctx.managed_task_status(),
                    'auth_enabled': self.ctx.auth_provider is not None,
                    'operator_view': {
                        'recommended_commands': [
                            'python install.py check',
                            'python install.py status',
                            'python install.py doctor',
                            'python install.py smoke',
                        ],
                        'recommended_runtime_checks': [
                            '/healthz for quick health state',
                            '/status for lifecycle, ownership, and service shape',
                            '/api/service/runtime for service-specific runtime visibility',
                        ],
                    },
                },
                request=request,
            )

        self.web_app.router.add_get('/healthz', healthz, name='landing_gear.healthz')
        self.web_app.router.add_get('/status', status, name='landing_gear.status')

    async def _on_cleanup(self, _app: web.Application) -> None:
        if self.module_manager is not None:
            self.ctx.record_lifecycle_event('service.stopping')
            await self.ctx.emit_hook('service.stopping')
            await self.module_manager.stop_all()
        managed_task_results = await self.ctx.stop_managed_tasks()
        self.ctx.state['managed_task_shutdown_results'] = managed_task_results
        self.ctx.record_lifecycle_event('service.stopped', managed_task_count=len(managed_task_results))
        await self.ctx.emit_hook('service.stopped')
