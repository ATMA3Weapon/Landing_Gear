# Landing Gear Hello Service Starter

A repo-ready starter for building small aiohttp services on top of the reusable Landing Gear kernel.

This repository intentionally contains **two layers**:

- `landing_gear/` — reusable kernel code you should keep generic
- `hello_service/` — example service code you are expected to rename and replace

The goal is to give you a template that is actually runnable, testable, packageable, and easy to fork into a real service.

## Who this is for

Use this starter when you want:

- a small Python service with an aiohttp HTTP surface
- a clean operator flow with `install.py`
- a reusable kernel layer separated from service-specific code
- a starting point you can publish as your own repo after renaming the example package

## What ships in this repo

- `landing_gear/` — config loading, runtime metadata, app assembly, install helpers
- `hello_service/` — example repository plus `hello` routes
- `service.py` — aiohttp application entrypoint
- `install.py` — CLI for check, doctor, status, readiness, smoke, and run
- `conf.example.toml` — commented template config for first setup
- `tests/` — regression, HTTP, config, hygiene, and packaging tests
- `.github/workflows/ci.yml` — CI for tests, operator checks, syntax compile, and package builds

## Prerequisites

- Python 3.11, 3.12, or 3.13
- `venv` support
- a shell that can run the commands below

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scriptsctivate
python -m pip install -U pip setuptools wheel
python -m pip install -e .
cp conf.example.toml conf.toml  # Windows: copy conf.example.toml conf.toml
python install.py check
python install.py smoke
python install.py run
```

Once the service is running, try:

```bash
curl http://127.0.0.1:8780/healthz
curl http://127.0.0.1:8780/status
curl "http://127.0.0.1:8780/api/hello?name=Erica"
curl -X POST http://127.0.0.1:8780/api/hello   -H "Content-Type: application/json"   -d '{"name": "Erica"}'
```

## First-run workflow

If you are turning this into a real service, do these in order:

1. Copy `conf.example.toml` to `conf.toml`.
2. Change `service.name` and `service.package_root`.
3. Follow `STARTER_RENAME_GUIDE.md` and rename `hello_service` to your real package.
4. Replace `hello_service/core_modules/hello.py` with your real endpoints.
5. Replace `hello_service/domain/repository.py` with your real domain storage and logic.
6. Update `README.md` and `pyproject.toml` before your first public commit.

## Operator commands

```bash
python install.py check
python install.py doctor
python install.py status
python install.py readiness
python install.py blueprint
python install.py reference
python install.py smoke
python install.py run
```

What each command is for:

- `check` — compact summary of repo and config health
- `doctor` — more detailed explanations for structural or config problems
- `status` — routes, ownership, lifecycle, and runtime metadata
- `readiness` — whether the repo is shaped well for reuse/publishing
- `blueprint` — expected files and package layout checks
- `reference` — guidance on what should stay generic vs be customized
- `smoke` — build the aiohttp app and immediately tear it down
- `run` — start the service

## HTTP surface

The example service exposes:

- `GET /healthz`
- `GET /status`
- `GET /api/hello?name=Erica`
- `POST /api/hello` with JSON `{"name": "Erica"}`
- `GET /api/hello/history?limit=10&offset=0`
- `GET /api/service/runtime`

Behavior notes:

- responses use an `{ok, result, meta}` style envelope on success
- bad JSON returns `400` with `code = "invalid_json"`
- unknown JSON fields on `POST /api/hello` return `400`
- invalid pagination values return `400`
- internal failures return a generic `internal error` response while the traceback stays in logs

## Repository layout and ownership

Keep these generic:

- `landing_gear/*`
- operator flow in `install.py`
- app assembly in `service.py`

Replace or rename these for your service:

- `hello_service/*`
- service identity fields in `conf.toml`
- service package metadata in `pyproject.toml`
- public endpoints, repository methods, and docs

## Files to edit first

1. `conf.toml`
2. `hello_service/core_modules/hello.py`
3. `hello_service/domain/repository.py`
4. `pyproject.toml`
5. `README.md`
6. `STARTER_RENAME_GUIDE.md`

## Config notes

Use `conf.example.toml` as the starting point.

Development-friendly defaults are intentional:

- auth disabled
- in-memory example repository
- TLS disabled

Before exposing a real service to other systems, revisit:

- `[auth]`
- `[tls]`
- `[outbound_tls]`
- module import paths after rename

## Local verification

Run the main local quality checks with:

```bash
python -m unittest discover -s tests -v
python install.py check
python install.py status
python install.py readiness
python install.py smoke
```

Optional packaging verification:

```bash
python -m pip install -e .[dev]
python -m build
```

## What the tests cover

- regressions from the original bug report
- aiohttp endpoint behavior
- config validation
- template hygiene against stale service names and phantom metadata
- packaging artifact inspection so built sdists/wheels do not carry `__pycache__` or `.pyc` junk

## CI behavior

The GitHub Actions workflow currently runs:

- the unittest suite
- `python install.py check`
- `python install.py status`
- `python install.py readiness`
- `python install.py smoke`
- `python -m compileall` against repo code
- `python -m pip check`
- `python -m build`

on Python 3.11, 3.12, and 3.13.

## Publishing and release flow

Before tagging a release:

```bash
python -m unittest discover -s tests -v
python install.py check
python install.py status
python install.py readiness
python install.py smoke
python -m build
```

Then:

1. update `CHANGELOG.md`
2. bump the version in `pyproject.toml`
3. verify `conf.example.toml` still matches the documented starter shape
4. make sure `STARTER_RENAME_GUIDE.md` still reflects the current package layout
5. create the tag only after CI is green

## Common pitfalls

- leaking service-specific names back into `landing_gear/`
- advertising routes in metadata that the service does not actually expose
- shipping local build/test junk such as `__pycache__` or `.pyc`
- forgetting to rename `hello_service` imports before publishing your own service
- copying `conf.toml` forward without updating package import paths

## Related docs

- `STARTER_RENAME_GUIDE.md` — rename walkthrough
- `SERVICE_SKELETON.md` — structural reference
- `SERVICE_BLUEPRINT_CHECKLIST.md` — starter shape checklist
- `CONTRIBUTING.md` — contribution expectations
- `CHANGELOG.md` — release notes
