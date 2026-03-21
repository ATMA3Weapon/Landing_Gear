# Starter Rename Guide

Use this checklist when turning the hello starter into a real service.

## 1. Rename the service identity

Edit `conf.toml` and `conf.example.toml`:

- `service.name`
- `service.package_root`
- `core_modules.*.import_path`

## 2. Rename the example package

Rename `hello_service/` to your real package name and update imports in:

- `service.py`
- `pyproject.toml`
- any module import paths in config
- tests that reference the example package

## 3. Replace the example domain

Replace or rewrite:

- `hello_service/core_modules/hello.py`
- `hello_service/domain/repository.py`

Keep the lifecycle pattern, route decorators, and context helpers. Replace the domain behavior.

## 4. Update repo metadata

Change:

- project name in `pyproject.toml`
- README examples and curl samples
- CHANGELOG heading if desired

## 5. Re-run the guardrails

After renaming, run:

```bash
python -m unittest discover -s tests -v
python install.py check
python install.py smoke
python -m build
```

## 6. Search for leftover example names

Before publishing, search the repo for:

- `hello_service`
- `hello-service`
- `/api/hello`

Only keep those if they are still intentionally part of your service.
