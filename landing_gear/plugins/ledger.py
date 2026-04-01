"""Ledger integration plugin for Landing Gear.

Per the spec (section 15.1):
  - Makes standard event emission easy for all services.
  - Packages foundry/event-envelope/v1 events.
  - Injects source identity and trace context where possible.
  - Supports tolerant (log-and-continue) or strict (raise) delivery.
  - Does NOT own event storage — Ledger service owns that.

Config section: ledger
  base_url  – required when plugin is enabled
  strict    – if true, delivery failures raise; default false (tolerant)
  timeout   – HTTP timeout seconds; default 5
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from .base import PluginBase

logger = logging.getLogger('landing_gear.plugins.ledger')

PLUGIN_ID = 'ledger'
EVENT_ENVELOPE_CONTRACT = 'foundry/event-envelope/v1'


class LedgerPlugin(PluginBase):
    """Wrap Ledger integration for event emission.

    Exposes emit_event() on the host context as ctx.ledger.emit_event().
    Also attaches itself as host_context.ledger so other modules can use it.
    """

    PLUGIN_ID = PLUGIN_ID
    DISPLAY_NAME = 'Ledger Integration'
    VERSION = '0.1.0'

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._base_url: str | None = None
        self._strict: bool = False
        self._timeout: int = 5
        self._service_id: str | None = None
        self._instance_id: str | None = None
        self._events_emitted: int = 0
        self._events_failed: int = 0
        self._session: Any = None

    async def startup(self, host_context: Any) -> None:
        import aiohttp
        self._base_url = self.config.get('base_url') or None
        self._strict = bool(self.config.get('strict', False))
        self._timeout = int(self.config.get('timeout', 5))
        self._service_id = getattr(host_context, 'service_id', None) or getattr(host_context, 'service_name', None)
        self._instance_id = getattr(host_context, 'instance_id', None)
        self._session = aiohttp.ClientSession()

        if not self._base_url:
            logger.warning('ledger plugin: base_url not configured — event emission disabled')

        # Attach self to host context so other plugins/modules can call emit_event
        if hasattr(host_context, 'set_component'):
            host_context.set_component(
                'ledger_plugin',
                self,
                kind='service_runtime',
                role='event_emitter',
                note='Ledger integration plugin',
            )

        # Expose shorthand on the context object directly
        try:
            host_context.ledger = self
        except (AttributeError, TypeError):
            pass

        await self._emit_boot_event(host_context)

    async def shutdown(self, host_context: Any) -> None:
        await self._emit_event_raw(
            event_type='foundry.service.stopping',
            payload={'service_id': self._service_id, 'instance_id': self._instance_id},
        )
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _build_envelope(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Wrap a payload in the foundry/event-envelope/v1 contract."""
        return {
            'contract': EVENT_ENVELOPE_CONTRACT,
            'event_id': str(uuid.uuid4()),
            'event_type': event_type,
            'at': datetime.now(timezone.utc).isoformat(),
            'source': {
                'service_id': self._service_id,
                'instance_id': self._instance_id,
            },
            'trace': {'correlation_id': correlation_id} if correlation_id else {},
            'payload': payload,
        }

    async def _emit_event_raw(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Attempt delivery to Ledger. Returns result dict."""
        if not self._base_url:
            return {'ok': False, 'reason': 'ledger base_url not configured'}

        envelope = self._build_envelope(event_type, payload, correlation_id=correlation_id)

        try:
            import aiohttp
            url = self._base_url.rstrip('/') + '/api/v1/events'
            async with self._session.post(
                url,
                json=envelope,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                    if resp.status in (200, 201, 202, 204):
                        self._events_emitted += 1
                        return {'ok': True, 'status': resp.status}
                    body = await resp.text()
                    raise RuntimeError(f'ledger returned {resp.status}: {body[:256]}')
        except Exception as exc:
            self._events_failed += 1
            msg = str(exc)
            logger.warning('ledger event delivery failed (%s): %s', event_type, msg)
            if self._strict:
                raise
            return {'ok': False, 'error': msg}

    async def emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Emit a foundry/event-envelope/v1 event to Ledger.

        Under tolerant mode (default), delivery failures are logged but do not
        raise. Under strict mode, failures propagate.
        """
        return await self._emit_event_raw(event_type, payload, correlation_id=correlation_id)

    async def _emit_boot_event(self, host_context: Any) -> None:
        await self._emit_event_raw(
            event_type='foundry.service.started',
            payload={
                'service_id': self._service_id,
                'instance_id': self._instance_id,
                'version': getattr(host_context, 'service_version', None),
            },
        )

    def enrich_status(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            'base_url': self._base_url,
            'strict': self._strict,
            'events_emitted': self._events_emitted,
            'events_failed': self._events_failed,
        }
