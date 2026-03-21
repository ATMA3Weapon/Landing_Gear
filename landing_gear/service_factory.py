from __future__ import annotations

from pathlib import Path
from typing import Any

from aiohttp import web

from .app import (
    KernelApp,
    LANDING_GEAR_CLIENT_SSL_CONTEXT_KEY,
    LANDING_GEAR_SERVER_SSL_CONTEXT_KEY,
)
from .auth import load_auth_provider
from .config import load_service_config, resolve_module_specs
from .context import ServiceContext
from .loader import ModuleManager
from .logging import configure_logging
from .tls import build_client_ssl_context, build_server_ssl_context


async def build_web_app_from_config(config_path: str | Path) -> web.Application:
    loaded = load_service_config(config_path)
    config = loaded.raw
    configure_logging(config.get('logging', {}).get('level', 'INFO'))
    ctx = ServiceContext(
        service_name=config['service']['name'],
        service_version=config['service']['version'],
        config=config,
        state={
            'config_path': str(loaded.source_path) if loaded.source_path else None,
            'env_overrides': list(loaded.applied_env_overrides),
        },
    )
    ctx.record_lifecycle_event('service.config_loaded', config_path=str(loaded.source_path) if loaded.source_path else None)
    for section in ctx.service_shape_model().kernel_config_sections:
        ctx.claim_config_section(section, owner='landing_gear', kind='kernel_config', note='kernel-owned config section')
    for section in ctx.service_shape_model().service_config_sections:
        ctx.claim_config_section(section, owner='service', kind='service_root', note='service-owned config section')
    ctx.auth_provider = load_auth_provider(config, ctx=ctx)
    ctx.set_client_ssl_context(build_client_ssl_context(config))
    manager = ModuleManager(ctx)
    ctx.record_lifecycle_event('service.module_loading_started')
    await manager.load(resolve_module_specs(config, 'core_modules'), kind='core')
    await manager.load(resolve_module_specs(config, 'plugins'), kind='plugin')
    ctx.record_lifecycle_event('service.module_loading_complete', module_count=len(ctx.loaded_modules))
    app = KernelApp(ctx, manager)
    app.bind_routes()
    app.add_builtin_status_routes()
    ctx.record_lifecycle_event('service.starting')
    await ctx.emit_hook('service.starting')
    await manager.start_all()
    await ctx.emit_hook('service.started')
    ctx.record_lifecycle_event('service.started')
    app.web_app[LANDING_GEAR_SERVER_SSL_CONTEXT_KEY] = build_server_ssl_context(config)
    app.web_app[LANDING_GEAR_CLIENT_SSL_CONTEXT_KEY] = ctx.client_ssl_context
    return app.web_app
