from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import BadRequestError

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(slots=True)
class BaseManifest:
    module_id: str
    name: str
    version: str
    description: str
    kind: str
    compatible_services: list[str] = field(default_factory=list)
    required_calls: list[str] = field(default_factory=list)
    required_scopes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PluginManifest(BaseManifest):
    kind: str = 'plugin'


@dataclass(slots=True)
class CoreModuleManifest(BaseManifest):
    kind: str = 'core'


def manifest_from_info(info: Any, *, compatible_services: list[str] | None = None) -> BaseManifest:
    services = compatible_services or []
    if getattr(info, 'kind', None) == 'plugin':
        return PluginManifest(
            module_id=info.id,
            name=info.name,
            version=info.version,
            description=info.description,
            compatible_services=services,
        )
    return CoreModuleManifest(
        module_id=info.id,
        name=info.name,
        version=info.version,
        description=info.description,
        compatible_services=services,
    )


def load_manifest_file(path: str | Path) -> BaseManifest:
    path = Path(path)
    with open(path, 'rb') as fh:
        data = tomllib.load(fh)
    manifest = data.get('manifest', data)
    kind = manifest.get('kind', 'core')
    cls = PluginManifest if kind == 'plugin' else CoreModuleManifest
    return cls(
        module_id=manifest['module_id'],
        name=manifest['name'],
        version=manifest['version'],
        description=manifest.get('description', ''),
        kind=kind,
        compatible_services=list(manifest.get('compatible_services', [])),
        required_calls=list(manifest.get('required_calls', [])),
        required_scopes=list(manifest.get('required_scopes', [])),
        tags=list(manifest.get('tags', [])),
    )


def resolve_manifest(
    *,
    manifest_path: str | Path | None,
    fallback_manifest: BaseManifest,
) -> BaseManifest:
    if manifest_path:
        return load_manifest_file(manifest_path)
    return fallback_manifest


def validate_manifest(
    manifest: BaseManifest,
    *,
    service_name: str,
    available_calls: list[str] | None = None,
) -> None:
    if manifest.compatible_services and service_name not in manifest.compatible_services:
        raise BadRequestError(
            f'module {manifest.module_id} is not compatible with service {service_name}',
            code='module_incompatible_service',
        )
    if available_calls is not None:
        missing = [name for name in manifest.required_calls if name not in available_calls]
        if missing:
            raise BadRequestError(
                f'module {manifest.module_id} is missing required calls: {", ".join(missing)}',
                code='module_missing_required_calls',
            )
