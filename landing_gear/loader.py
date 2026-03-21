from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

from .config import ModuleSpec
from .errors import BadRequestError
from .manifests import manifest_from_info, resolve_manifest, validate_manifest
from .modules import BaseModule


class ModuleManager:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.modules: list[BaseModule] = []
        self._loaded_names: set[str] = set()
        self._loaded_ids: set[str] = set()

    def _infer_manifest_path(self, module: Any, spec: ModuleSpec) -> str | None:
        if spec.manifest_path:
            return spec.manifest_path
        module_file = getattr(module, '__file__', None)
        if not module_file:
            return None
        module_path = Path(module_file)
        candidates = [
            module_path.with_name(f'{module_path.stem}.manifest.toml'),
            module_path.with_name('manifest.toml'),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    async def load(self, module_specs: list[ModuleSpec], *, kind: str) -> list[BaseModule]:
        loaded: list[BaseModule] = []
        for spec in module_specs:
            missing_deps = [dep for dep in spec.depends_on if dep not in self._loaded_names and dep not in self._loaded_ids]
            if missing_deps:
                raise BadRequestError(
                    f'module {spec.name} has unresolved dependencies: {", ".join(missing_deps)}',
                    code='module_missing_dependency',
                )

            module = importlib.import_module(spec.import_path)
            cls = getattr(module, spec.class_name)
            instance: BaseModule = cls(self.ctx, spec.config)
            config_section_path = f'{kind}s.{spec.name}'
            setattr(instance, '_lg_config_section_path', config_section_path)
            module_id = instance.INFO.id
            self.ctx.claim_config_section(config_section_path, owner=module_id, kind='module_config', note=f'{kind} module config')
            fallback_manifest = getattr(cls, 'MANIFEST', None) or manifest_from_info(
                instance.INFO,
                compatible_services=spec.compatible_services,
            )
            manifest = resolve_manifest(
                manifest_path=self._infer_manifest_path(module, spec),
                fallback_manifest=fallback_manifest,
            )
            validate_manifest(
                manifest,
                service_name=self.ctx.service_name,
                available_calls=sorted(self.ctx.calls.calls.keys()),
            )
            self.ctx.record_module_state(
                module_id,
                kind=kind,
                name=spec.name,
                class_name=spec.class_name,
                import_path=spec.import_path,
                configured=True,
                phase='configured',
                depends_on=list(spec.depends_on),
                manifest={
                    'module_id': manifest.module_id,
                    'name': manifest.name,
                    'version': manifest.version,
                    'kind': manifest.kind,
                    'compatible_services': manifest.compatible_services,
                    'required_calls': manifest.required_calls,
                    'required_scopes': manifest.required_scopes,
                    'tags': manifest.tags,
                },
            )
            try:
                await instance.setup()
                self.ctx.record_module_state(module_id, setup_complete=True, phase='setup_complete', ownership={'repositories_expected': True, 'managed_tasks_expected_after_start': True})
                self.ctx.record_lifecycle_event('module.setup_complete', module_id=module_id, kind=kind)
                instance.register()
                self.ctx.record_module_state(module_id, registered=True, phase='registered')
                self.ctx.record_lifecycle_event('module.registered', module_id=module_id, kind=kind)
                loaded.append(instance)
                self.modules.append(instance)
                self.ctx.loaded_modules.append(instance)
                self._loaded_names.add(spec.name)
                self._loaded_ids.add(module_id)
            except Exception as exc:
                self.ctx.record_module_state(module_id, phase='failed', last_error=str(exc))
                self.ctx.record_lifecycle_event('module.start_failed', module_id=instance.INFO.id, kind=instance.INFO.kind, error=str(exc))
                raise
        return loaded

    async def start_all(self) -> None:
        for module in self.modules:
            try:
                await module.start()
                self.ctx.record_module_state(module.INFO.id, started=True, phase='started')
                self.ctx.record_lifecycle_event('module.started', module_id=module.INFO.id, kind=module.INFO.kind)
            except Exception as exc:
                self.ctx.record_module_state(module.INFO.id, phase='failed', last_error=str(exc))
                self.ctx.record_lifecycle_event('module.start_failed', module_id=module.INFO.id, kind=module.INFO.kind, error=str(exc))
                raise
        self.ctx.record_lifecycle_event('service.modules_started', module_count=len(self.modules))
        startup_results = await self.ctx.tasks.run_startup()
        self.ctx.state['startup_results'] = startup_results

    async def stop_all(self) -> None:
        self.ctx.record_lifecycle_event('service.shutdown_tasks_starting', module_count=len(self.modules))
        shutdown_results = await self.ctx.tasks.run_shutdown()
        self.ctx.state['shutdown_results'] = shutdown_results
        for module in reversed(self.modules):
            try:
                await module.stop()
                self.ctx.record_module_state(module.INFO.id, stopped=True, phase='stopped')
                self.ctx.record_lifecycle_event('module.stopped', module_id=module.INFO.id, kind=module.INFO.kind)
            except Exception as exc:
                self.ctx.record_module_state(module.INFO.id, phase='failed', last_error=str(exc))
                self.ctx.record_lifecycle_event('module.stop_failed', module_id=module.INFO.id, kind=module.INFO.kind, error=str(exc))
                raise

    async def collect_health(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for module in self.modules:
            try:
                health = await module.health()
                results[module.INFO.id] = health
                self.ctx.record_module_state(module.INFO.id, healthy=bool(health.get('ok', False)))
            except Exception as exc:
                results[module.INFO.id] = {'ok': False, 'error': str(exc)}
                self.ctx.record_module_state(module.INFO.id, healthy=False, last_error=str(exc))
        return results
