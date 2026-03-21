from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib


ConfigDict = dict[str, Any]


@dataclass(slots=True)
class ModuleSpec:
    name: str
    import_path: str
    class_name: str
    config: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    compatible_services: list[str] = field(default_factory=list)
    manifest_path: str | None = None


@dataclass(slots=True)
class ServiceConfig:
    raw: ConfigDict
    source_path: Path | None = None
    applied_env_overrides: list[str] = field(default_factory=list)

    @property
    def service(self) -> ConfigDict:
        return get_section(self.raw, 'service')

    @property
    def logging(self) -> ConfigDict:
        return get_section(self.raw, 'logging')

    @property
    def auth(self) -> ConfigDict:
        return get_section(self.raw, 'auth')

    @property
    def tls(self) -> ConfigDict:
        return get_section(self.raw, 'tls')

    @property
    def outbound_tls(self) -> ConfigDict:
        return get_section(self.raw, 'outbound_tls')


def load_toml(path: str | Path) -> ConfigDict:
    with open(path, 'rb') as fh:
        return tomllib.load(fh)


def load_service_config(path: str | Path) -> ServiceConfig:
    path = Path(path)
    config = load_toml(path)
    applied_env_overrides = apply_env_overrides(config)
    resolve_relative_paths(config, path.parent)
    validate_service_config(config)
    return ServiceConfig(raw=config, source_path=path, applied_env_overrides=applied_env_overrides)


def get_section(config: ConfigDict, name: str) -> ConfigDict:
    value = config.get(name, {})
    if not isinstance(value, dict):
        raise TypeError(f'config section is not a mapping: {name}')
    return value


def apply_env_overrides(config: ConfigDict) -> list[str]:
    service = config.setdefault('service', {})
    applied: list[str] = []
    if os.getenv('LANDING_GEAR_HOST'):
        service['host'] = os.environ['LANDING_GEAR_HOST']
        applied.append('LANDING_GEAR_HOST')
    if os.getenv('LANDING_GEAR_PORT'):
        service['port'] = int(os.environ['LANDING_GEAR_PORT'])
        applied.append('LANDING_GEAR_PORT')
    if os.getenv('LANDING_GEAR_LOG_LEVEL'):
        config.setdefault('logging', {})['level'] = os.environ['LANDING_GEAR_LOG_LEVEL']
        applied.append('LANDING_GEAR_LOG_LEVEL')
    if os.getenv('LANDING_GEAR_TLS_ENABLED'):
        config.setdefault('tls', {})['enabled'] = os.environ['LANDING_GEAR_TLS_ENABLED'].lower() in {'1', 'true', 'yes', 'on'}
        applied.append('LANDING_GEAR_TLS_ENABLED')
    if os.getenv('LANDING_GEAR_TLS_CERT_FILE'):
        config.setdefault('tls', {})['cert_file'] = os.environ['LANDING_GEAR_TLS_CERT_FILE']
        applied.append('LANDING_GEAR_TLS_CERT_FILE')
    if os.getenv('LANDING_GEAR_TLS_KEY_FILE'):
        config.setdefault('tls', {})['key_file'] = os.environ['LANDING_GEAR_TLS_KEY_FILE']
        applied.append('LANDING_GEAR_TLS_KEY_FILE')
    if os.getenv('LANDING_GEAR_TLS_CA_FILE'):
        config.setdefault('tls', {})['ca_file'] = os.environ['LANDING_GEAR_TLS_CA_FILE']
        applied.append('LANDING_GEAR_TLS_CA_FILE')
    return applied


def resolve_relative_paths(config: ConfigDict, base_dir: Path) -> None:
    path_fields = {
        ('tls', 'cert_file'),
        ('tls', 'key_file'),
        ('tls', 'ca_file'),
        ('outbound_tls', 'cert_file'),
        ('outbound_tls', 'key_file'),
        ('outbound_tls', 'ca_file'),
        ('hub', 'storage', 'path'),
    }
    for parts in path_fields:
        section = config
        for key in parts[:-1]:
            value = section.get(key)
            if not isinstance(value, dict):
                section = None
                break
            section = value
        if not isinstance(section, dict):
            continue
        field_name = parts[-1]
        value = section.get(field_name)
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = Path(value)
        if not candidate.is_absolute():
            section[field_name] = str((base_dir / candidate).resolve())


def validate_service_config(config: ConfigDict) -> None:
    service = get_section(config, 'service')
    name = service.get('name')
    if not isinstance(name, str) or not name.strip():
        raise ValueError('service.name must be a non-empty string')
    version = service.get('version')
    if not isinstance(version, str) or not version.strip():
        raise ValueError('service.version must be a non-empty string')
    for optional_field in ('package_root', 'entrypoint', 'install_flow', 'kernel_package', 'core_modules_package', 'plugins_package', 'domain_package', 'repositories_package', 'schemas_package', 'states_package'):
        value = service.get(optional_field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f'service.{optional_field} must be a non-empty string when set')
    host = service.get('host', '127.0.0.1')
    if not isinstance(host, str) or not host.strip():
        raise ValueError('service.host must be a non-empty string')
    port = service.get('port', 8080)
    if not isinstance(port, int) or port <= 0 or port > 65535:
        raise ValueError('service.port must be an integer between 1 and 65535')

    logging_section = get_section(config, 'logging')
    level = str(logging_section.get('level', 'INFO')).upper()
    if level not in {'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'}:
        raise ValueError('logging.level must be one of CRITICAL, ERROR, WARNING, INFO, DEBUG')

    auth_section = get_section(config, 'auth')
    if auth_section.get('enabled'):
        provider_path = auth_section.get('provider_path')
        static_tokens = auth_section.get('static_tokens', {})
        if provider_path is not None and not isinstance(provider_path, str):
            raise ValueError('auth.provider_path must be a string when set')
        if provider_path is None and static_tokens and not isinstance(static_tokens, dict):
            raise ValueError('auth.static_tokens must be a mapping of token -> identity config')

    for section_name in ('core_modules', 'plugins'):
        section = get_section(config, section_name)
        for key, value in section.items():
            if not isinstance(value, dict):
                raise ValueError(f'{section_name}.{key} must be a mapping')
            if value.get('enabled', True) is False:
                continue
            import_path = value.get('import_path')
            class_name = value.get('class_name')
            if not isinstance(import_path, str) or not import_path.strip():
                raise ValueError(f'{section_name}.{key}.import_path must be a non-empty string')
            if not isinstance(class_name, str) or not class_name.strip():
                raise ValueError(f'{section_name}.{key}.class_name must be a non-empty string')
            depends_on = value.get('depends_on', [])
            if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
                raise ValueError(f'{section_name}.{key}.depends_on must be a list of strings')


def resolve_module_specs(config: ConfigDict, section_name: str) -> list[ModuleSpec]:
    section = get_section(config, section_name)
    specs: list[ModuleSpec] = []
    for key, value in section.items():
        if not isinstance(value, dict):
            continue
        if value.get('enabled', True) is False:
            continue
        import_path = value.get('import_path')
        class_name = value.get('class_name')
        if not import_path or not class_name:
            raise ValueError(
                f'module config {section_name}.{key} must define import_path and class_name'
            )
        module_config = {
            k: v
            for k, v in value.items()
            if k not in {
                'enabled', 'import_path', 'class_name', 'depends_on', 'compatible_services', 'manifest_path'
            }
        }
        depends_on = list(value.get('depends_on', []))
        specs.append(
            ModuleSpec(
                name=key,
                import_path=import_path,
                class_name=class_name,
                config=module_config,
                depends_on=depends_on,
                compatible_services=list(value.get('compatible_services', [])),
                manifest_path=value.get('manifest_path'),
            )
        )
    return sort_module_specs(specs)


def sort_module_specs(specs: list[ModuleSpec]) -> list[ModuleSpec]:
    by_name = {spec.name: spec for spec in specs}
    ordered: list[ModuleSpec] = []
    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(spec: ModuleSpec) -> None:
        if spec.name in permanent:
            return
        if spec.name in temporary:
            raise ValueError(f'circular module dependency detected at: {spec.name}')
        temporary.add(spec.name)
        for dep in spec.depends_on:
            if dep not in by_name:
                continue
            visit(by_name[dep])
        temporary.remove(spec.name)
        permanent.add(spec.name)
        ordered.append(spec)

    for spec in specs:
        visit(spec)
    return ordered
