# Landing Gear Hello Service Starter

A small but real Landing Gear starter repo that separates the reusable kernel from the example service built on top of it.

- `landing_gear/` — generic kernel code shared across services
- `hello_service/` — example domain package, repository, and routes
- `service.py` — aiohttp application entrypoint
- `install.py` — operator CLI for check, doctor, smoke, status, and run
- `conf.example.toml` — commented template config

## What this repo is for

Use this repo as the starting point for a new service. Copy the repo shape and operator flow first, then replace the example service pieces with your own domain logic.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -U pip setuptools wheel
python -m pip install -e .
cp conf.example.toml conf.toml  # Windows: copy conf.example.toml conf.toml
python install.py check
python install.py smoke
python install.py run
```

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

What each one does:

- `check` gives a compact summary of the current service state
- `doctor` explains config and structural issues in more detail
- `status` shows routes, ownership, lifecycle, and runtime metadata
- `readiness` scores whether the repo is shaped well for reuse
- `blueprint` checks expected files and packages
- `reference` explains what should be copied vs adapted for a new service
- `smoke` builds the aiohttp app and immediately tears it down
- `run` starts the service

## HTTP surface

The example service exposes:

- `GET /healthz`
- `GET /status`
- `GET /api/hello?name=Erica`
- `POST /api/hello` with JSON `{"name": "Erica"}`
- `GET /api/hello/history?limit=10&offset=0`
- `GET /api/service/runtime`

Example calls:

```bash
curl http://127.0.0.1:8780/healthz
curl http://127.0.0.1:8780/status
curl "http://127.0.0.1:8780/api/hello?name=Erica"
curl -X POST http://127.0.0.1:8780/api/hello -H "Content-Type: application/json" -d '{"name": "Erica"}'
```

## Files to edit first when turning this into a real service

1. `conf.toml`
2. `hello_service/core_modules/hello.py`
3. `hello_service/domain/repository.py`
4. `README.md`
5. `pyproject.toml`
6. `STARTER_RENAME_GUIDE.md`

## Framework code vs example code

Keep these generic:

- `landing_gear/*`
- operator flow in `install.py`
- app creation in `service.py`

Replace or rename these per service:

- `hello_service/*`
- service name, package root, and module config in `conf.toml`
- public endpoints and repository methods

## Tests

Run the full local test pass with:

```bash
python -m unittest discover -s tests -v
python install.py smoke
python install.py check
```

The test suite covers:

- runtime regressions from the original bug report
- HTTP endpoint behavior
- config validation
- starter hygiene around runtime metadata

## Packaging

This repo includes source-distribution hygiene rules and CI that builds both an sdist and a wheel. For local build validation, install the optional dev tools and run:

```bash
python -m pip install -e .[dev]
python -m build
```

## Publish checklist

Before tagging a release, verify:

```bash
python -m unittest discover -s tests -v
python install.py check
python install.py smoke
python -m build
```

## Common pitfalls

- Do not put service-specific names back into `landing_gear/`
- Do not advertise routes in metadata that the service does not actually expose
- Keep config examples commented and readable instead of duplicating live config verbatim
- Treat `landing_gear/` as shared kernel code and move domain rules into the service package


## Rename this starter into your own service

There is now a dedicated walkthrough in `STARTER_RENAME_GUIDE.md`. Follow it before your first public commit so you do not leave `hello_service` names behind in package imports, config, and docs.

## Production-hardening notes

This starter intentionally ships with development-friendly defaults:

- auth disabled
- in-memory state for the example repository
- TLS disabled

Before running a real service for other clients or systems, review those surfaces and replace the example defaults with service-specific choices.


## Local config workflow
- Commit `conf.example.toml` as the documented template.
- Keep your working `conf.toml` local and out of version control.
- Create it by copying the example before first run.

## Health checks and auth
- `/healthz` and `/status` are intended for operator and probe access.
- The middleware skips authentication for those built-in routes so load balancer or orchestrator health checks do not fail when service auth is enabled.
