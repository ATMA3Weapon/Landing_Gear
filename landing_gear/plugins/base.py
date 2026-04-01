"""Plugin base interface for Landing Gear first-party plugins.

Per the spec, the plugin system must be explicit, deterministic, and reviewable.
Each plugin declares its identity, config expectations, and lifecycle surfaces.

Plugin lifecycle surfaces (section 14.3):
  startup(host_context)         – init clients, warm state, validate config
  shutdown(host_context)        – clean teardown, close clients
  register_routes(app)          – add explicit routes if the plugin exposes them
  register_middleware(app)      – attach request middleware such as auth guards
  enrich_status(snapshot)       – add status/debug fields to service status output
  helpers/clients               – expose runtime helper objects to host context
"""
from __future__ import annotations

from typing import Any


class PluginBase:
    """Base class for all Landing Gear first-party plugins.

    Subclasses must define PLUGIN_ID, DISPLAY_NAME, and VERSION as class
    attributes. All lifecycle methods are optional no-ops by default.
    """

    PLUGIN_ID: str = ''
    DISPLAY_NAME: str = ''
    VERSION: str = '0.1.0'

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}
        self._enabled: bool = True
        self._error: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle

    async def startup(self, host_context: Any) -> None:
        """Initialize clients, warm state, emit boot events, validate config."""

    async def shutdown(self, host_context: Any) -> None:
        """Clean teardown and close clients."""

    # ------------------------------------------------------------------
    # HTTP integration

    def register_routes(self, app: Any) -> None:
        """Add explicit routes if the plugin is meant to expose them."""

    def register_middleware(self, app: Any) -> None:
        """Attach request middleware such as auth guards."""

    # ------------------------------------------------------------------
    # Observability

    def enrich_status(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Add status/debug fields to the service status output.

        Return a dict of key->value pairs to merge into the plugin section
        of /api/v1/status.
        """
        return {}

    # ------------------------------------------------------------------
    # Internal state

    def mark_error(self, error: str) -> None:
        self._error = error
        self._enabled = False

    def status_summary(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            'plugin_id': self.PLUGIN_ID,
            'display_name': self.DISPLAY_NAME,
            'version': self.VERSION,
            'enabled': self._enabled,
        }
        if self._error:
            base['error'] = self._error
        base.update(self.enrich_status({}))
        return base
