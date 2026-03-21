# Changelog

## 0.1.3
- removed accidental `__pycache__` and `.pyc` files from the published starter tree
- added a packaging-artifact test that inspects built sdists and wheels for junk files
- expanded the README into a fuller first-time-user guide and release workflow reference
- added a dedicated `RELEASE_CHECKLIST.md`
- tightened CI with `compileall` and `pip check`

Unreleased

- tightened POST /api/hello input contract by rejecting unknown fields
- added HTTP tests for invalid pagination and extra JSON fields
- stopped returning raw exception text in 500 responses
- added a starter rename guide and improved config placeholders
- expanded CI to Python 3.11, 3.12, and 3.13 with status/readiness checks
