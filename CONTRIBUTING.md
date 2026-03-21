# Contributing

## Local development

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -U pip setuptools wheel
python -m pip install -e .[dev]
```

## Before opening a change

Run:

```bash
python -m unittest discover -s tests -v
python install.py check
python install.py smoke
python -m build
```

## Contribution rules

- keep `landing_gear/` generic
- put service-specific behavior under the service package
- add regression tests for every bug fix
- do not add phantom routes or stale sibling-service names to runtime metadata
