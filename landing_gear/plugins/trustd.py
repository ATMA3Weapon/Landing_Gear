"""Trustd integration plugin for Landing Gear.

Per the spec (section 15.2):
  - General Trustd integration for trust-aware services.
  - Provides helpers for service enrollment, manifest verification,
    trust verdict retrieval, capability checks, trust context access.
  - Does NOT become a second trust authority — it is a client/integration layer.
  - Trustd owns trust and auth. This plugin only provides the surface to
    consume Trustd consistently.

Config section: trustd
  base_url  – required when plugin is enabled
  timeout   – HTTP timeout seconds; default 5
"""
from __future__ import annotations

import logging
from typing import Any

from .base import PluginBase

logger = logging.getLogger('landing_gear.plugins.trustd')

PLUGIN_ID = 'trustd'
TRUST_VERDICT_CONTRACT = 'foundry/trust-verdict/v1'
IDENTITY_RECORD_CONTRACT = 'foundry/identity-record/v1'


class TrustdPlugin(PluginBase):
    """Wrap general Trustd integration and verification helpers.

    Exposes verify_manifest(), check_capability(), and get_trust_verdict()
    for modules and other plugins to use via host_context.trustd.
    """

    PLUGIN_ID = PLUGIN_ID
    DISPLAY_NAME = 'Trustd Integration'
    VERSION = '0.1.0'

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._base_url: str | None = None
        self._timeout: int = 5
        self._service_id: str | None = None
        self._enrolled: bool = False
        self._session: Any = None

    async def startup(self, host_context: Any) -> None:
        import aiohttp
        self._base_url = self.config.get('base_url') or None
        self._timeout = int(self.config.get('timeout', 5))
        self._service_id = (
            getattr(host_context, 'service_id', None)
            or getattr(host_context, 'service_name', None)
        )
        self._session = aiohttp.ClientSession()

        if not self._base_url:
            logger.warning('trustd plugin: base_url not configured — trust integration disabled')
            return

        if hasattr(host_context, 'set_component'):
            host_context.set_component(
                'trustd_plugin',
                self,
                kind='service_runtime',
                role='trust_client',
                note='Trustd integration plugin',
            )

        try:
            host_context.trustd = self
        except (AttributeError, TypeError):
            pass

        await self._attempt_enrollment(host_context)

    async def shutdown(self, host_context: Any) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _attempt_enrollment(self, host_context: Any) -> None:
        """Attempt to register or verify this service with Trustd."""
        if not self._base_url:
            return
        try:
            manifest = None
            if hasattr(host_context, 'service_manifest'):
                manifest = host_context.service_manifest()
            result = await self._post(
                '/api/v1/enroll',
                {
                    'service_id': self._service_id,
                    'version': getattr(host_context, 'service_version', None),
                    'manifest': manifest,
                },
            )
            if result.get('ok'):
                self._enrolled = True
                logger.info('trustd: service enrolled successfully')
            else:
                logger.warning('trustd: enrollment returned non-ok: %s', result)
        except Exception as exc:
            logger.warning('trustd: enrollment failed (non-fatal): %s', exc)

    async def verify_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Submit a service manifest to Trustd for verification.

        Returns a foundry/trust-verdict/v1 dict.
        """
        return await self._post('/api/v1/verify/manifest', {'manifest': manifest})

    async def check_capability(self, subject: str, capability: str) -> dict[str, Any]:
        """Check whether a subject has a capability via Trustd."""
        return await self._post('/api/v1/capabilities/check', {
            'subject': subject,
            'capability': capability,
        })

    async def get_trust_verdict(self, subject: str) -> dict[str, Any]:
        """Retrieve a trust verdict for a given subject from Trustd."""
        return await self._get(f'/api/v1/trust/verdict/{subject}')

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._base_url:
            return {'ok': False, 'reason': 'trustd base_url not configured'}
        try:
            import aiohttp
            url = self._base_url.rstrip('/') + path
            async with self._session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                data = await resp.json()
                return data if isinstance(data, dict) else {'ok': True, 'result': data}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    async def _get(self, path: str) -> dict[str, Any]:
        if not self._base_url:
            return {'ok': False, 'reason': 'trustd base_url not configured'}
        try:
            import aiohttp
            url = self._base_url.rstrip('/') + path
            async with self._session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                data = await resp.json()
                return data if isinstance(data, dict) else {'ok': True, 'result': data}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def enrich_status(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            'base_url': self._base_url,
            'enrolled': self._enrolled,
        }
