from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from .config import load_service_config, resolve_module_specs
from .config_profile import build_config_profile
from .service_shape import build_service_shape
from .tls import describe_tls_state


AppFactory = Callable[[str | Path], Awaitable[web.Application]]


def _repo_root_from_config(config_path: str | Path) -> Path:
    return Path(config_path).resolve().parent


def build_reference_service_guidance(config_path: str | Path, raw_config: dict[str, Any]) -> dict[str, Any]:
    blueprint = build_service_blueprint_report(config_path, raw_config)
    shape = build_service_shape(raw_config)
    contract = shape.contract_summary()
    return {
        'service_name': shape.service_name,
        'reference_service': shape.package_root,
        'copy_as_is': contract.get('copy_as_is_for_new_services', []),
        'adapt_per_service': contract.get('adapt_per_service', []),
        'do_not_copy': contract.get('do_not_copy_from_reference_service', []),
        'reference_boundaries': {
            'kernel': shape.kernel_package,
            'core_modules': f"{shape.package_root}/{shape.core_modules_package}",
            'plugins': f"{shape.package_root}/{shape.plugins_package}",
            'domain_package': f"{shape.package_root}/{shape.domain_package}",
        },
        'recommended_new_service_steps': [
            'copy the repo shape and operator flow first',
            'rename the package root and domain package for the new service',
            'remove example service domain modules you do not need',
            'keep landing_gear generic; move new domain rules into the new service domain package',
            'build one small core module at a time and keep setup/register/start/stop explicit',
            'run install.py doctor, readiness, smoke, and status before adding more features',
        ],
        'blueprint_ready': blueprint['ready'],
    }
def build_service_blueprint_report(config_path: str | Path, raw_config: dict[str, Any]) -> dict[str, Any]:
    root = _repo_root_from_config(config_path)
    shape = build_service_shape(raw_config)
    package_root_dir = root / shape.package_root
    expected_files = {
        'entrypoint': root / shape.entrypoint,
        'install_flow': root / shape.install_flow,
        'config': root / Path(config_path).name,
        'package_root': package_root_dir,
        'kernel_package': root / shape.kernel_package,
        'core_modules_package': package_root_dir / shape.core_modules_package,
        'plugins_package': package_root_dir / shape.plugins_package,
        'domain_package': package_root_dir / shape.domain_package,
    }
    checks = []
    missing = []
    for name, path in expected_files.items():
        exists = path.exists()
        checks.append({'name': name, 'path': str(path), 'exists': exists})
        if not exists:
            missing.append(name)
    return {
        'repo_root': str(root),
        'package_root': str(package_root_dir),
        'checks': checks,
        'missing': missing,
        'ready': not missing,
        'service_contract': shape.contract_summary(),
        'builder_checklist': [
            'declare service shape in conf.toml',
            'keep landing_gear generic and reusable',
            'keep service domain logic in the service-owned domain package',
            'create repositories in module setup()',
            'register routes and hooks in module register()',
            'start long-lived loops only in module start()',
            'use install.py doctor, status, smoke, and run before packaging',
        ],
    }


def build_service_readiness_report(config_path: str | Path, raw_config: dict[str, Any], *, env_overrides: list[str] | None = None) -> dict[str, Any]:
    blueprint = build_service_blueprint_report(config_path, raw_config)
    profile = build_config_profile(raw_config, env_overrides=env_overrides)
    core_specs = resolve_module_specs(raw_config, 'core_modules')
    plugin_specs = resolve_module_specs(raw_config, 'plugins')
    checks = {
        'blueprint_ready': blueprint['ready'],
        'core_modules_present': bool(core_specs),
        'config_has_auth_section': 'auth' in raw_config,
        'service_shape_declared': bool(raw_config.get('service', {}).get('package_root')),
        'operator_entrypoints_present': all(item['exists'] for item in blueprint['checks'] if item['name'] in {'entrypoint', 'install_flow', 'config'}),
    }
    warnings: list[str] = []
    if not profile['auth_enabled']:
        warnings.append('auth is disabled')
    if not profile['core_modules_enabled']:
        warnings.append('no core modules are enabled')
    if profile['storage_backend'] == 'memory':
        warnings.append('storage backend is memory; good for development, not ideal for long-running service state')
    if env_overrides:
        warnings.append('environment overrides are active; packaging should not depend on hidden local env state')
    score = sum(1 for value in checks.values() if value) / max(1, len(checks))
    return {
        'ready': all(checks.values()),
        'score': round(score, 2),
        'checks': checks,
        'warnings': warnings,
        'config_profile': profile,
        'config_ownership': build_config_ownership_report(raw_config),
        'enabled_modules': {
            'core': [spec.name for spec in core_specs],
            'plugins': [spec.name for spec in plugin_specs],
        },
    }




def build_config_ownership_report(raw_config: dict[str, Any]) -> dict[str, Any]:
    shape = build_service_shape(raw_config)
    top_level_keys = sorted(raw_config.keys()) if isinstance(raw_config, dict) else []
    kernel_sections = {name: {'exists': name in raw_config, 'owner': 'landing_gear'} for name in shape.kernel_config_sections}
    service_sections = {name: {'exists': name in raw_config, 'owner': 'service'} for name in shape.service_config_sections}
    unclassified_top_level = [
        key for key in top_level_keys
        if key not in set(shape.kernel_config_sections) and key not in set(shape.service_config_sections)
    ]
    return {
        'kernel_sections': kernel_sections,
        'service_sections': service_sections,
        'unclassified_top_level': unclassified_top_level,
        'ownership_rule': 'landing_gear owns kernel config sections; the service owns core_modules/plugins and any additional domain config',
    }

def load_service_metadata(config_path: str | Path) -> dict[str, Any]:
    loaded = load_service_config(config_path)
    service = loaded.service
    shape_model = build_service_shape(loaded.raw)
    service_shape = shape_model.to_dict()
    service_contract = shape_model.contract_summary()
    config_profile = build_config_profile(loaded.raw, env_overrides=loaded.applied_env_overrides)
    readiness = build_service_readiness_report(config_path, loaded.raw, env_overrides=loaded.applied_env_overrides)
    config_ownership = build_config_ownership_report(loaded.raw)
    return {
        'name': service.get('name', 'unknown'),
        'version': service.get('version', '0.0.0'),
        'host': service.get('host', '127.0.0.1'),
        'port': service.get('port', 0),
        'config_path': str(Path(config_path)),
        'env_overrides': list(loaded.applied_env_overrides),
        'tls': describe_tls_state(loaded.raw),
        'core_modules': [spec.name for spec in resolve_module_specs(loaded.raw, 'core_modules')],
        'plugins': [spec.name for spec in resolve_module_specs(loaded.raw, 'plugins')],
        'service_shape': service_shape,
        'service_contract': service_contract,
        'config_profile': config_profile,
        'service_blueprint': build_service_blueprint_report(config_path, loaded.raw),
        'service_readiness': readiness,
        'reference_service_guidance': build_reference_service_guidance(config_path, loaded.raw),
        'config_ownership': config_ownership,
        'operator_commands': ['python install.py check', 'python install.py status', 'python install.py doctor', 'python install.py smoke', 'python install.py blueprint', 'python install.py readiness', 'python install.py reference', 'python install.py run'],
        'runtime_views': {
            'generic_service_runtime': '/status',
            'generic_service_health': '/healthz',
            'service_runtime': '/api/service/runtime',
        },
    }



def build_operator_check_report(config_path: str | Path) -> dict[str, Any]:
    metadata = load_service_metadata(config_path)
    doctor_report = doctor(config_path)
    return {
        'ok': bool(doctor_report.get('ok', False)),
        'service': {
            'name': metadata['name'],
            'version': metadata['version'],
            'config_path': metadata['config_path'],
        },
        'config_profile': metadata['config_profile'],
        'readiness': metadata['service_readiness'],
        'blueprint_ready': metadata['service_blueprint']['ready'],
        'runtime_views': metadata['runtime_views'],
        'service_contract': metadata['service_contract'],
        'issues': doctor_report.get('issues', []),
        'warnings': doctor_report.get('warnings', []),
        'recommended_commands': metadata['operator_commands'],
    }

def print_status(config_path: str | Path) -> dict[str, Any]:
    return load_service_metadata(config_path)


async def smoke_check(app_factory: AppFactory, config_path: str | Path) -> dict[str, Any]:
    app = await app_factory(config_path)
    ok = isinstance(app, web.Application)
    await app.cleanup()
    return {'ok': ok, 'kind': app.__class__.__name__}


def run_smoke(app_factory: AppFactory, config_path: str | Path) -> dict[str, Any]:
    return asyncio.run(smoke_check(app_factory, config_path))


def run_service(app_factory: AppFactory, config_path: str | Path) -> None:
    loaded = load_service_config(config_path)
    config = loaded.raw
    app = asyncio.run(app_factory(config_path))
    web.run_app(
        app,
        host=config['service'].get('host', '127.0.0.1'),
        port=config['service'].get('port', 8080),
        ssl_context=app.get('landing_gear_server_ssl_context'),
    )


def doctor(config_path: str | Path) -> dict[str, Any]:
    loaded = load_service_config(config_path)
    service = loaded.service
    tls = describe_tls_state(loaded.raw)
    issues: list[str] = []
    notes: list[str] = []
    warnings: list[str] = []
    if not service.get('name'):
        issues.append('service.name is missing')
    if not service.get('version'):
        issues.append('service.version is missing')
    if tls['inbound']['enabled'] and (not tls['inbound']['cert_file'] or not tls['inbound']['key_file']):
        issues.append('tls.enabled=true requires tls.cert_file and tls.key_file')

    auth_config = loaded.raw.get('auth', {}) or {}
    if auth_config.get('enabled'):
        if auth_config.get('provider_path'):
            notes.append(f"custom auth provider: {auth_config.get('provider_path')}")
        elif auth_config.get('static_tokens'):
            notes.append('auth uses static bearer tokens')
        else:
            issues.append('auth.enabled=true but no auth provider is configured')
    else:
        warnings.append('auth is disabled')

    blueprint = build_service_blueprint_report(config_path, loaded.raw)
    if blueprint['missing']:
        warnings.append('service blueprint is missing some expected paths: ' + ', '.join(blueprint['missing']))

    readiness = build_service_readiness_report(config_path, loaded.raw, env_overrides=loaded.applied_env_overrides)
    config_ownership = build_config_ownership_report(loaded.raw)
    warnings.extend(item for item in readiness['warnings'] if item not in warnings)

    try:
        core_modules = [spec.name for spec in resolve_module_specs(loaded.raw, 'core_modules')]
        plugins = [spec.name for spec in resolve_module_specs(loaded.raw, 'plugins')]
        service_shape = build_service_shape(loaded.raw).to_dict()
        config_profile = build_config_profile(loaded.raw, env_overrides=loaded.applied_env_overrides)
        notes.append(f'core modules: {", ".join(core_modules) or "none"}')
        notes.append(f'plugins: {", ".join(plugins) or "none"}')
        notes.append(
            'service skeleton: ' +
            f"entrypoint={service_shape['entrypoint']}, install_flow={service_shape['install_flow']}, " +
            f"package_root={service_shape['package_root']}, kernel_package={service_shape['kernel_package']}"
        )
        notes.append(
            'config profile: ' +
            f"auth={config_profile['auth_mode']}, tls_enabled={config_profile['tls_enabled']}, " +
            f"storage_backend={config_profile['storage_backend']}"
        )
        if loaded.applied_env_overrides:
            notes.append('environment overrides applied: ' + ', '.join(loaded.applied_env_overrides))
    except Exception as exc:
        issues.append(f'module config invalid: {exc}')

    return {
        'ok': not issues,
        'issues': issues,
        'warnings': warnings,
        'notes': notes,
        'tls': tls,
        'config_profile': build_config_profile(loaded.raw, env_overrides=loaded.applied_env_overrides),
        'config_ownership': config_ownership,
        'service_blueprint': blueprint,
        'service_readiness': readiness,
        'reference_service_guidance': build_reference_service_guidance(config_path, loaded.raw),
        'recommended_next_checks': [
            'run python install.py check for a compact operator summary',
            'run python install.py reference to review what to copy versus what to replace for a new service',
            'run python install.py status to inspect service shape and ownership',
            'run python install.py readiness to score multi-service reuse readiness',
            'run python install.py smoke after module or config changes',
            'check /status while the service is running to verify lifecycle, ownership, and config profile',
            'check /api/service/runtime for service-specific runtime state and scaffolding ownership',
        ],
    }


def build_install_cli(app_factory: AppFactory, default_config_path: str | Path):
    parser = argparse.ArgumentParser()
    parser.add_argument('command', nargs='?', default='status', choices=['status', 'smoke', 'run', 'doctor', 'blueprint', 'readiness', 'reference', 'check'])
    parser.add_argument('--config', default=str(default_config_path))

    def _emit(payload: dict[str, Any]) -> None:
        print(json.dumps(payload, indent=2, sort_keys=True))

    def main(argv: list[str] | None = None):
        args = parser.parse_args(argv)
        if args.command == 'status':
            _emit(print_status(args.config))
            return
        if args.command == 'smoke':
            _emit(run_smoke(app_factory, args.config))
            return
        if args.command == 'run':
            run_service(app_factory, args.config)
            return
        if args.command == 'doctor':
            _emit(doctor(args.config))
            return
        if args.command == 'blueprint':
            loaded = load_service_config(args.config)
            _emit(build_service_blueprint_report(args.config, loaded.raw))
            return
        if args.command == 'readiness':
            loaded = load_service_config(args.config)
            _emit(build_service_readiness_report(args.config, loaded.raw, env_overrides=loaded.applied_env_overrides))
            return
        if args.command == 'reference':
            loaded = load_service_config(args.config)
            _emit(build_reference_service_guidance(args.config, loaded.raw))
            return
        if args.command == 'check':
            _emit(build_operator_check_report(args.config))
            return

    return main
