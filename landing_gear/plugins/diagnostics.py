"""Diagnostics plugin for Landing Gear (optional).

Per the spec (section 15.4):
  - Status enrichment, runtime metadata, version/build info,
    and lightweight diagnostics.
  - Optional in the first pass but useful as a place for diagnostics hooks.
"""
from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from typing import Any

from .base import PluginBase

PLUGIN_ID = 'diagnostics'


class DiagnosticsPlugin(PluginBase):
    """Optional status enrichment and runtime metadata plugin."""

    PLUGIN_ID = PLUGIN_ID
    DISPLAY_NAME = 'Diagnostics'
    VERSION = '0.1.0'

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._started_at: str | None = None
        self._build_info: dict[str, Any] = {}

    async def startup(self, host_context: Any) -> None:
        self._started_at = datetime.now(timezone.utc).isoformat()

        # Collect build info from host context if available
        self._build_info = {
            'service_version': getattr(host_context, 'service_version', None),
            'python_version': sys.version,
            'platform': platform.platform(),
        }

        # Allow the host context to provide additional build metadata
        if hasattr(host_context, 'config'):
            cfg = host_context.config or {}
            build_cfg = cfg.get('build', {}) if isinstance(cfg, dict) else {}
            if isinstance(build_cfg, dict):
                self._build_info.update(build_cfg)

        if hasattr(host_context, 'set_component'):
            host_context.set_component(
                'diagnostics_plugin',
                self,
                kind='service_runtime',
                role='diagnostics',
                note='Diagnostics and build info plugin',
            )

    async def shutdown(self, host_context: Any) -> None:
        pass

    def enrich_status(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            'started_at': self._started_at,
            'build_info': self._build_info,
        }
