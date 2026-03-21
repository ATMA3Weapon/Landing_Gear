# Release Checklist

Use this before publishing a release or cutting a public starter tag.

## Verify locally

```bash
python -m unittest discover -s tests -v
python install.py check
python install.py status
python install.py readiness
python install.py smoke
python -m build
```

## Review starter quality

- Confirm `conf.example.toml` is commented and matches the current package layout.
- Confirm `STARTER_RENAME_GUIDE.md` still matches the rename path from `hello_service` to a real service.
- Confirm no stale names or phantom routes were introduced.
- Confirm the built sdist and wheel do not contain `__pycache__`, `.pyc`, or local packaging junk.

## Publish steps

1. Update `CHANGELOG.md`.
2. Bump `version` in `pyproject.toml`.
3. Push the branch and wait for CI to pass.
4. Create the release tag only after CI is green.
