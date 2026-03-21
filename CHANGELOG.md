# Changelog

## Unreleased

- tightened POST /api/hello input contract by rejecting unknown fields
- added HTTP tests for invalid pagination and extra JSON fields
- stopped returning raw exception text in 500 responses
- added a starter rename guide and improved config placeholders
- expanded CI to Python 3.11, 3.12, and 3.13 with status/readiness checks


## Unreleased
- Fixed the loader setup-failure path to record lifecycle events from the module instance instead of the imported Python module object.
- Removed dead context access from request error middleware.
- Exempted built-in `/healthz` and `/status` routes from auth middleware so health probes keep working when auth is enabled.
- Stopped committing a live `conf.toml`; the repo now prefers `conf.example.toml` and ignores local `conf.toml`.
- Updated docs and tests for the safer local-config workflow.
