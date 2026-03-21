from __future__ import annotations

from typing import Any


def build_config_profile(raw_config: dict[str, Any], *, env_overrides: list[str] | None = None, service_name: str | None = None, service_version: str | None = None) -> dict[str, Any]:
    service = raw_config.get('service', {}) if isinstance(raw_config.get('service', {}), dict) else {}
    auth = raw_config.get('auth', {}) if isinstance(raw_config.get('auth', {}), dict) else {}
    tls = raw_config.get('tls', {}) if isinstance(raw_config.get('tls', {}), dict) else {}
    outbound_tls = raw_config.get('outbound_tls', {}) if isinstance(raw_config.get('outbound_tls', {}), dict) else {}
    core_modules = raw_config.get('core_modules', {}) if isinstance(raw_config.get('core_modules', {}), dict) else {}
    plugins = raw_config.get('plugins', {}) if isinstance(raw_config.get('plugins', {}), dict) else {}
    storage = raw_config.get('storage', {}) if isinstance(raw_config.get('storage', {}), dict) else {}

    enabled_core = sorted(
        name for name, section in core_modules.items()
        if isinstance(section, dict) and section.get('enabled', True) is not False
    )
    enabled_plugins = sorted(
        name for name, section in plugins.items()
        if isinstance(section, dict) and section.get('enabled', True) is not False
    )

    return {
        'service_name': service_name or str(service.get('name', 'service')),
        'service_version': service_version or str(service.get('version', '0.0.0')),
        'package_root': str(service.get('package_root') or service.get('python_package') or service.get('name', 'service')),
        'auth_enabled': bool(auth.get('enabled', False)),
        'auth_mode': 'custom_provider' if auth.get('provider_path') else ('static_tokens' if auth.get('static_tokens') else 'disabled'),
        'tls_enabled': bool(tls.get('enabled', False)),
        'outbound_tls_enabled': bool(outbound_tls.get('enabled', False)),
        'core_modules_enabled': enabled_core,
        'plugins_enabled': enabled_plugins,
        'storage_backend': str(storage.get('backend', 'memory')),
        'env_overrides': list(env_overrides or []),
    }
