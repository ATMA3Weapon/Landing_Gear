from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import find_overlapping_queue_settings
from .tls import describe_tls_state


def _resolve_runtime_profile(raw_config: dict[str, Any], *, service_name: str) -> dict[str, Any]:
    hub = raw_config.get('hub', {}) if isinstance(raw_config.get('hub', {}), dict) else {}
    core_modules = raw_config.get('core_modules', {}) if isinstance(raw_config.get('core_modules', {}), dict) else {}
    queue = core_modules.get('queue', {}) if isinstance(core_modules.get('queue', {}), dict) else {}
    storage = hub.get('storage', {}) if isinstance(hub.get('storage', {}), dict) else {}
    retention = hub.get('retention', {}) if isinstance(hub.get('retention', {}), dict) else {}

    lease_ttl_seconds = int(queue.get('lease_ttl_seconds', hub.get('lease_ttl_seconds', 90)))
    stale_worker_seconds = int(queue.get('stale_worker_seconds', hub.get('stale_worker_seconds', lease_ttl_seconds * 2)))
    enable_housekeeping = bool(queue.get('enable_housekeeping', True))
    housekeeping_interval_seconds = int(queue.get('housekeeping_interval_seconds', 30))

    backend = str(storage.get('backend', 'memory')).strip().lower()
    default_path = Path('var') / f'{service_name}.sqlite3'
    raw_path = storage.get('path') or str(default_path)
    storage_path = str(raw_path) if backend == 'sqlite' else None

    audit_max_events = max(100, int(retention.get('audit_max_events', queue.get('audit_max_events', 1000))))
    terminal_job_max_age_seconds = max(3600, int(retention.get('terminal_job_max_age_seconds', queue.get('terminal_job_max_age_seconds', 7 * 24 * 60 * 60))))
    terminal_job_max_count = max(100, int(retention.get('terminal_job_max_count', queue.get('terminal_job_max_count', 5000))))

    return {
        'storage_backend': backend,
        'storage_path': storage_path,
        'queue': {
            'lease_ttl_seconds': lease_ttl_seconds,
            'stale_worker_seconds': stale_worker_seconds,
            'enable_housekeeping': enable_housekeeping,
            'housekeeping_interval_seconds': housekeeping_interval_seconds,
        },
        'retention': {
            'audit_max_events': audit_max_events,
            'terminal_job_max_age_seconds': terminal_job_max_age_seconds,
            'terminal_job_max_count': terminal_job_max_count,
        },
    }


def build_config_profile(raw_config: dict[str, Any], *, env_overrides: list[str] | None = None, service_name: str | None = None, service_version: str | None = None) -> dict[str, Any]:
    service = raw_config.get('service', {}) if isinstance(raw_config, dict) else {}
    auth = raw_config.get('auth', {}) if isinstance(raw_config.get('auth', {}), dict) else {}
    tls = describe_tls_state(raw_config)
    core_modules = raw_config.get('core_modules', {}) if isinstance(raw_config.get('core_modules', {}), dict) else {}
    plugins = raw_config.get('plugins', {}) if isinstance(raw_config.get('plugins', {}), dict) else {}
    resolved_service_name = service_name or service.get('name', 'unknown')
    runtime_profile = _resolve_runtime_profile(raw_config, service_name=resolved_service_name)
    overlapping_queue_settings = find_overlapping_queue_settings(raw_config)
    return {
        'service_name': resolved_service_name,
        'service_version': service_version or service.get('version', '0.0.0'),
        'package_root': str(service.get('package_root', 'service')),
        'auth_enabled': bool(auth.get('enabled', False)),
        'auth_mode': 'custom_provider' if auth.get('provider_path') else ('static_tokens' if auth.get('static_tokens') else 'disabled'),
        'tls_enabled': bool(tls['inbound']['enabled']),
        'outbound_tls_enabled': bool(tls['outbound']['enabled']),
        'storage_backend': runtime_profile['storage_backend'],
        'storage_path': runtime_profile['storage_path'],
        'queue': runtime_profile['queue'],
        'retention': runtime_profile['retention'],
        'config_conflicts': {
            'overlapping_queue_settings': overlapping_queue_settings,
        },
        'core_modules_enabled': sorted([name for name, value in core_modules.items() if isinstance(value, dict) and value.get('enabled', True) is not False]),
        'plugins_enabled': sorted([name for name, value in plugins.items() if isinstance(value, dict) and value.get('enabled', True) is not False]),
        'env_overrides': list(env_overrides or []),
    }
