"""Smoke tests for Landing Gear framework validation.

Per the spec (§18, testing/smoke.py):
  Provide simple executable smoke checks that validate the framework is wired
  correctly before running full integration tests.

Usage:
    python -m landing_gear.testing.smoke http://127.0.0.1:8780

Each check hits a standard endpoint and validates the response shape.
All checks must pass for the smoke run to succeed.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any


_CHECKS: list[tuple[str, str]] = [
    ('healthz',          '/healthz'),
    ('readyz',           '/readyz'),
    ('status_v1',        '/api/v1/status'),
    ('service_manifest', '/.well-known/foundry/service.json'),
]


async def _get(session, url: str) -> tuple[int, Any]:
    async with session.get(url) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = await resp.text()
        return resp.status, data


def _check_healthz(status: int, data: Any) -> list[str]:
    errors = []
    if status not in (200, 503):
        errors.append(f'expected 200 or 503, got {status}')
    if not isinstance(data, dict):
        errors.append('response must be a JSON object')
    elif 'ok' not in data:
        errors.append('response missing "ok" field')
    return errors


def _check_readyz(status: int, data: Any) -> list[str]:
    errors = []
    if status not in (200, 503):
        errors.append(f'expected 200 or 503, got {status}')
    if not isinstance(data, dict):
        errors.append('response must be a JSON object')
        return errors
    # Support both envelope {'ok':..,'result':{'ready':..}} and flat {'ready':..}
    result = data.get('result', data)
    if not isinstance(result, dict) or 'ready' not in result:
        errors.append('response missing "ready" field')
    return errors


def _check_status_v1(status: int, data: Any) -> list[str]:
    errors = []
    if status != 200:
        errors.append(f'expected 200, got {status}')
    if not isinstance(data, dict):
        errors.append('response must be a JSON object')
        return errors
    result = data.get('result', data)
    for field in ('service', 'version', 'instance_id'):
        if field not in result:
            errors.append(f'status response missing field: {field}')
    return errors


def _check_service_manifest(status: int, data: Any) -> list[str]:
    errors = []
    if status != 200:
        errors.append(f'expected 200, got {status}')
    if not isinstance(data, dict):
        errors.append('response must be a JSON object')
        return errors
    result = data.get('result', data)
    contract = result.get('contract')
    if contract != 'foundry/service-manifest/v1':
        errors.append(f'expected contract foundry/service-manifest/v1, got {contract!r}')
    for field in ('service_id', 'service_name', 'version', 'endpoints'):
        if field not in result:
            errors.append(f'service manifest missing field: {field}')
    endpoints = result.get('endpoints', {})
    for ep in ('healthz', 'readyz', 'status', 'manifest'):
        if ep not in endpoints:
            errors.append(f'service manifest endpoints missing: {ep}')
    return errors


_VALIDATORS = {
    'healthz':          _check_healthz,
    'readyz':           _check_readyz,
    'status_v1':        _check_status_v1,
    'service_manifest': _check_service_manifest,
}


async def run_smoke(base_url: str) -> dict[str, Any]:
    """Run all smoke checks against a running service.

    Returns a dict of check_name -> {ok, status, errors}.
    """
    import aiohttp

    base = base_url.rstrip('/')
    results: dict[str, Any] = {}
    failed = 0

    async with aiohttp.ClientSession() as session:
        for name, path in _CHECKS:
            url = base + path
            try:
                status, data = await _get(session, url)
                validator = _VALIDATORS.get(name)
                errors = validator(status, data) if validator else []
                ok = len(errors) == 0
            except Exception as exc:
                ok = False
                errors = [str(exc)]
                status = 0

            results[name] = {'ok': ok, 'path': path, 'http_status': status, 'errors': errors}
            if not ok:
                failed += 1

    results['_summary'] = {
        'total': len(_CHECKS),
        'passed': len(_CHECKS) - failed,
        'failed': failed,
        'all_ok': failed == 0,
    }
    return results


def print_results(results: dict[str, Any]) -> None:
    summary = results.pop('_summary', {})
    for name, result in results.items():
        icon = '✓' if result['ok'] else '✗'
        print(f'  {icon}  {name:<25} {result["path"]}  (HTTP {result["http_status"]})')
        for err in result.get('errors', []):
            print(f'       ERROR: {err}')
    print()
    print(f'  {summary.get("passed", 0)}/{summary.get("total", 0)} checks passed')
    if not summary.get('all_ok'):
        print('  SMOKE FAILED')
    else:
        print('  SMOKE PASSED')


async def _main(base_url: str) -> int:
    print(f'\nLanding Gear smoke checks → {base_url}\n')
    results = await run_smoke(base_url)
    summary_ok = results.get('_summary', {}).get('all_ok', False)
    print_results(results)
    return 0 if summary_ok else 1


if __name__ == '__main__':
    url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8780'
    sys.exit(asyncio.run(_main(url)))
