## [0.2.0] - 2026-11-27

### Added
- `pyproject.toml` for `pip install -e .` support.
- `ARCHITECTURE.md` explaining `BEGIN IMMEDIATE` guarantees.
- `ReplyStore` context manager (`__enter__` / `__exit__`).
- Explicit `session_id` type validation.
- Stress, persistence, and `SQLITE_BUSY` regression tests.
- `ruff` and `mypy` checks in CI.


# Changelog

## 0.1.0 - 2026-11-27

### Added

- Transactional validation of active sessions.
- Protection against delayed replies after deletion.
- Atomic cascading deletion.
- Concurrent write and delete regression tests.
- Independent process testing.
- Transaction rollback and data integrity checks.
- Unicode support.
- GitHub Actions automated testing.
- MIT license and contribution guidelines.

### Verified

- 16 regression tests passed on each Python version.
- Python 3.10, 3.11, 3.12, 3.13 and 3.14.
- 80 successful test executions in total.

### Limitations

- Experimental SQLite reference implementation.
- No verified external adoption yet.
- Not a production-ready security library.
