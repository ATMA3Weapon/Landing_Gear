from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ModuleInfo:
    id: str
    name: str
    version: str
    description: str
    kind: str  # core or plugin


@dataclass(slots=True)
class ModuleRuntimeState:
    module_id: str
    kind: str
    class_name: str
    import_path: str
    configured: bool = True
    setup_complete: bool = False
    registered: bool = False
    started: bool = False
    stopped: bool = False
    healthy: bool | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseModule:
    INFO: ModuleInfo

    def __init__(self, ctx: 'ServiceContext', config: dict[str, Any] | None = None) -> None:
        self.ctx = ctx
        self.config = config or {}

    @property
    def module_id(self) -> str:
        return self.INFO.id

    def set_repository(self, name: str, repo: Any) -> None:
        self.ctx.set_repository(name, repo, owner=self.module_id)

    def set_component(self, name: str, value: Any, *, kind: str = 'service_component', role: str | None = None, note: str | None = None) -> None:
        self.ctx.set_component(name, value, owner=self.module_id, kind=kind, role=role, note=note)

    def claim_config_section(self, path: str, *, kind: str = 'module_config', note: str | None = None) -> None:
        self.ctx.claim_config_section(path, owner=self.module_id, kind=kind, note=note)

    def start_managed_task(self, name: str, coro: Any):
        return self.ctx.start_managed_task(name, coro, owner=self.module_id)

    def register_startup_task(self, name: str, handler) -> None:
        self.ctx.register_startup_task(name, handler, owner=self.module_id)

    def register_shutdown_task(self, name: str, handler) -> None:
        self.ctx.register_shutdown_task(name, handler, owner=self.module_id)

    async def setup(self) -> None:
        """Prepare internal state before registration. Own repositories here."""

    def register(self) -> None:
        """Register routes, hooks, calls, and startup/shutdown hooks here."""

    async def start(self) -> None:
        """Start managed background behavior after registration only."""

    async def stop(self) -> None:
        """Stop module-owned behavior cleanly."""

    async def health(self) -> dict[str, Any]:
        return {'ok': True, 'module': self.INFO.id}


class CoreModule(BaseModule):
    """Built-in service module."""


class PluginModule(BaseModule):
    """Optional or shared extension module."""


from .context import ServiceContext  # noqa: E402
