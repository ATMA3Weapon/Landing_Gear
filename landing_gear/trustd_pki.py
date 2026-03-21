from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class CertificateRequest:
    common_name: str
    san_dns: list[str] = field(default_factory=list)
    san_ip: list[str] = field(default_factory=list)
    ttl_hours: int = 24 * 30
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IssuedCertificate:
    certificate_pem: str
    private_key_pem: str | None = None
    ca_bundle_pem: str | None = None
    serial_number: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TrustRegistrar(Protocol):
    async def issue_service_certificate(self, request: CertificateRequest) -> IssuedCertificate: ...
    async def revoke_certificate(self, serial_number: str, reason: str | None = None) -> dict[str, Any]: ...
    async def get_trust_bundle(self) -> str: ...


class NullTrustRegistrar:
    async def issue_service_certificate(self, request: CertificateRequest) -> IssuedCertificate:
        raise NotImplementedError('Trustd PKI is not enabled yet')

    async def revoke_certificate(self, serial_number: str, reason: str | None = None) -> dict[str, Any]:
        raise NotImplementedError('Trustd PKI is not enabled yet')

    async def get_trust_bundle(self) -> str:
        raise NotImplementedError('Trustd PKI is not enabled yet')
