"""Plugin registry for Landing Gear.

Per the spec (section 14.2):
  - Plugins load in a deterministic order.
  - The enabled list comes from config or explicit service registration.
  - The registry detects duplicate plugin IDs.
  - Startup failures are logged clearly and either fail fast or degrade
    explicitly depending on config.
  - Plugin status is inspectable at /api/v1/status.
  - Plugins are individually testable.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import PluginBase

logger = logging.getLogger('landing_gear.plugins')


class PluginRegistry:
    """Manages plugin registration, ordering, startup, and teardown."""

    def __init__(self, *, fail_fast: bool = True) -> None:
        self._plugins: list[PluginBase] = []
        self._by_id: dict[str, PluginBase] = {}
        self._fail_fast = fail_fast

    def register(self, plugin: PluginBase) -> None:
        """Register a plugin instance. Raises on duplicate plugin_id."""
        pid = plugin.PLUGIN_ID
        if not pid:
            raise ValueError(f'plugin {type(plugin).__name__} has no PLUGIN_ID')
        if pid in self._by_id:
            raise ValueError(f'duplicate plugin_id: {pid}')
        self._plugins.append(plugin)
        self._by_id[pid] = plugin
        logger.debug('plugin registered: %s (%s)', pid, plugin.DISPLAY_NAME)

    def get(self, plugin_id: str) -> PluginBase | None:
        return self._by_id.get(plugin_id)

    def all(self) -> list[PluginBase]:
        return list(self._plugins)

    async def startup_all(self, host_context: Any) -> dict[str, Any]:
        """Run startup on all registered plugins in registration order."""
        results: dict[str, Any] = {}
        for plugin in self._plugins:
            pid = plugin.PLUGIN_ID
            try:
                await plugin.startup(host_context)
                results[pid] = {'ok': True}
                logger.info('plugin started: %s', pid)
            except Exception as exc:
                msg = str(exc)
                plugin.mark_error(msg)
                results[pid] = {'ok': False, 'error': msg}
                logger.error('plugin startup failed: %s — %s', pid, msg)
                if self._fail_fast:
                    raise
        return results

    async def shutdown_all(self, host_context: Any) -> dict[str, Any]:
        """Run shutdown on all registered plugins in reverse order."""
        results: dict[str, Any] = {}
        for plugin in reversed(self._plugins):
            pid = plugin.PLUGIN_ID
            try:
                await plugin.shutdown(host_context)
                results[pid] = {'ok': True}
                logger.info('plugin stopped: %s', pid)
            except Exception as exc:
                msg = str(exc)
                results[pid] = {'ok': False, 'error': msg}
                logger.error('plugin shutdown failed: %s — %s', pid, msg)
        return results

    def register_all_routes(self, app: Any) -> None:
        for plugin in self._plugins:
            plugin.register_routes(app)

    def register_all_middleware(self, app: Any) -> None:
        for plugin in self._plugins:
            plugin.register_middleware(app)

    def status_snapshot(self) -> dict[str, Any]:
        return {p.PLUGIN_ID: p.status_summary() for p in self._plugins}
