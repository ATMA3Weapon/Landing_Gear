# Service Skeleton

Recommended repo shape for a Landing Gear service:

- `landing_gear/` — shared kernel
- `<service_package>/core_modules/` — service API and runtime modules
- `<service_package>/plugins/` — optional edge-facing extensions
- `<service_package>/domain/` — repositories, schemas, states, policy, domain helpers
- `service.py` — app factory entrypoint
- `install.py` — operator/install CLI
- `conf.toml` — service config

## Lifecycle contract

- `setup()`
  - build internal state
  - create repositories
  - claim module-owned config where needed
- `register()`
  - register routes, calls, hooks, health checks, startup/shutdown tasks
- `start()`
  - start managed long-lived background work
- `stop()`
  - stop managed work cleanly

## Keep this boundary clean

- kernel owns lifecycle, middleware, registries, request/response helpers, auth seam, TLS seam, status/doctor support
- service owns routes, repositories, domain logic, runtime policy, and service-specific config
