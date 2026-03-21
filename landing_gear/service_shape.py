from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class ServiceShape:
    service_name: str
    package_root: str
    entrypoint: str = 'service.py'
    install_flow: str = 'install.py'
    kernel_package: str = 'landing_gear'
    core_modules_package: str = 'core_modules'
    plugins_package: str = 'plugins'
    domain_package: str = 'domain'
    repositories_package: str = 'domain'
    schemas_package: str = 'domain'
    states_package: str = 'domain'
    repositories_note: str = 'domain persistence lives outside the kernel'
    kernel_config_sections: tuple[str, ...] = ('service', 'logging', 'auth', 'tls', 'outbound_tls')
    service_config_sections: tuple[str, ...] = ('core_modules', 'plugins')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def contract_summary(self) -> dict[str, Any]:
        return {
            'copy_as_is_for_new_services': [
                'service.py install.py conf.toml and conf.example.toml lifecycle pattern',
                'landing_gear package structure and generic helpers',
                'core_modules and plugins package convention',
                'module setup/register/start/stop ownership pattern',
                'doctor/status/smoke/readiness operator flow',
            ],
            'adapt_per_service': [
                f'domain package name and contents: {self.domain_package}',
                'service-specific config sections under the service-owned config surface',
                'repositories, domain schemas, states, and policies',
                'core modules exposing the service API surface',
                'plugins only when they clearly belong at the edge',
            ],
            'do_not_copy_from_reference_service': [
                'service-specific routes and semantics from the example service without reviewing your own domain needs',
                'example retention or storage defaults without reviewing service needs',
                'example admin endpoints for unrelated services',
                'domain types from another service package into unrelated services',
            ],
            'kernel_owns': [
                'app factory and middleware',
                'config loading and validation',
                'route/hook/call/task registries',
                'module and plugin lifecycle',
                'module ownership and managed task supervision',
                'request/response helpers',
                'health, status, and doctor support',
                'auth and TLS seams',
            ],
            'kernel_config_sections': list(self.kernel_config_sections),
            'service_config_sections': list(self.service_config_sections),
            'service_owns': [
                f'domain package: {self.domain_package}',
                f'repositories package: {self.repositories_package}',
                f'schemas package: {self.schemas_package}',
                f'states package: {self.states_package}',
                f'core modules package: {self.core_modules_package}',
                f'plugins package: {self.plugins_package}',
                'module-owned repositories and managed tasks',
                'service-owned runtime components distinct from repositories',
            ],
            'runtime_surface_split': {
                'generic_service_surface': ['/healthz', '/status'],
                'service_runtime_surface': ['/api/service/runtime'],
                'service_domain_runtime_surface': ['service-defined runtime and diagnostics endpoints'],
            },
        }


def build_service_shape(config: dict[str, Any]) -> ServiceShape:
    service = config.get('service', {}) if isinstance(config, dict) else {}
    service_name = str(service.get('name', 'service'))
    package_root = str(service.get('package_root') or service.get('python_package') or 'service')
    entrypoint = str(service.get('entrypoint') or 'service.py')
    install_flow = str(service.get('install_flow') or 'install.py')
    kernel_package = str(service.get('kernel_package') or 'landing_gear')
    core_modules_package = str(service.get('core_modules_package') or 'core_modules')
    plugins_package = str(service.get('plugins_package') or 'plugins')
    domain_package = str(service.get('domain_package') or 'domain')
    repositories_package = str(service.get('repositories_package') or domain_package)
    schemas_package = str(service.get('schemas_package') or domain_package)
    states_package = str(service.get('states_package') or domain_package)
    repositories_note = str(service.get('repositories_note') or 'domain persistence lives outside the kernel')
    return ServiceShape(
        service_name=service_name,
        package_root=package_root,
        entrypoint=entrypoint,
        install_flow=install_flow,
        kernel_package=kernel_package,
        core_modules_package=core_modules_package,
        plugins_package=plugins_package,
        domain_package=domain_package,
        repositories_package=repositories_package,
        schemas_package=schemas_package,
        states_package=states_package,
        repositories_note=repositories_note,
    )
