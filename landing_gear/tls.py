from __future__ import annotations

import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import BadRequestError

TLS_VERSION_MAP: dict[str, ssl.TLSVersion] = {
    "TLSv1_2": ssl.TLSVersion.TLSv1_2,
    "TLSv1_3": ssl.TLSVersion.TLSv1_3,
}


@dataclass(slots=True)
class TLSSettings:
    enabled: bool = False
    cert_file: str | None = None
    key_file: str | None = None
    ca_file: str | None = None
    minimum_version: str = "TLSv1_2"
    require_client_cert: bool = False


@dataclass(slots=True)
class OutboundTLSSettings:
    enabled: bool = False
    ca_file: str | None = None
    cert_file: str | None = None
    key_file: str | None = None
    verify_hostname: bool = True
    minimum_version: str = "TLSv1_2"


def _validate_file(path: str | None, label: str) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise BadRequestError(f'{label} does not exist: {path}', code='tls_file_missing')
    return str(p)


def _get_version(name: str) -> ssl.TLSVersion:
    try:
        return TLS_VERSION_MAP[name]
    except KeyError as exc:
        raise BadRequestError(f'unsupported TLS version: {name}', code='tls_version_invalid') from exc


def load_tls_settings(config: dict[str, Any]) -> TLSSettings:
    section = config.get('tls', {}) or {}
    return TLSSettings(
        enabled=bool(section.get('enabled', False)),
        cert_file=section.get('cert_file'),
        key_file=section.get('key_file'),
        ca_file=section.get('ca_file'),
        minimum_version=str(section.get('minimum_version', 'TLSv1_2')),
        require_client_cert=bool(section.get('require_client_cert', False)),
    )


def load_outbound_tls_settings(config: dict[str, Any]) -> OutboundTLSSettings:
    section = config.get('outbound_tls', {}) or {}
    return OutboundTLSSettings(
        enabled=bool(section.get('enabled', False)),
        ca_file=section.get('ca_file'),
        cert_file=section.get('cert_file'),
        key_file=section.get('key_file'),
        verify_hostname=bool(section.get('verify_hostname', True)),
        minimum_version=str(section.get('minimum_version', 'TLSv1_2')),
    )


def build_server_ssl_context(config: dict[str, Any]) -> ssl.SSLContext | None:
    settings = load_tls_settings(config)
    if not settings.enabled:
        return None
    cert_file = _validate_file(settings.cert_file, 'TLS cert_file')
    key_file = _validate_file(settings.key_file, 'TLS key_file')
    if not cert_file or not key_file:
        raise BadRequestError('tls.enabled requires cert_file and key_file', code='tls_config_invalid')
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.minimum_version = _get_version(settings.minimum_version)
    ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
    if settings.ca_file:
        ctx.load_verify_locations(cafile=_validate_file(settings.ca_file, 'TLS ca_file'))
    if settings.require_client_cert:
        if not settings.ca_file:
            raise BadRequestError(
                'require_client_cert=true requires ca_file',
                code='tls_client_ca_missing',
            )
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def build_client_ssl_context(config: dict[str, Any]) -> ssl.SSLContext | None:
    settings = load_outbound_tls_settings(config)
    if not settings.enabled:
        return None
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.minimum_version = _get_version(settings.minimum_version)
    if settings.ca_file:
        ctx.load_verify_locations(cafile=_validate_file(settings.ca_file, 'Outbound TLS ca_file'))
    if settings.cert_file or settings.key_file:
        cert_file = _validate_file(settings.cert_file, 'Outbound TLS cert_file')
        key_file = _validate_file(settings.key_file, 'Outbound TLS key_file')
        if not cert_file or not key_file:
            raise BadRequestError(
                'outbound_tls cert_file and key_file must both be set',
                code='outbound_tls_config_invalid',
            )
        ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
    ctx.check_hostname = settings.verify_hostname
    if not settings.verify_hostname:
        ctx.verify_mode = ssl.CERT_REQUIRED if settings.ca_file else ssl.CERT_NONE
    return ctx


def describe_tls_state(config: dict[str, Any]) -> dict[str, Any]:
    inbound = load_tls_settings(config)
    outbound = load_outbound_tls_settings(config)
    return {
        'inbound': {
            'enabled': inbound.enabled,
            'minimum_version': inbound.minimum_version,
            'cert_file': inbound.cert_file,
            'key_file': inbound.key_file,
            'ca_file': inbound.ca_file,
            'require_client_cert': inbound.require_client_cert,
        },
        'outbound': {
            'enabled': outbound.enabled,
            'minimum_version': outbound.minimum_version,
            'ca_file': outbound.ca_file,
            'cert_file': outbound.cert_file,
            'key_file': outbound.key_file,
            'verify_hostname': outbound.verify_hostname,
        },
    }
