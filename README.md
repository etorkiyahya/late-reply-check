# late-reply-check

[![Tests](https://github.com/etorkiyahya/late-reply-check/actions/workflows/tests.yml/badge.svg)](https://github.com/etorkiyahya/late-reply-check/actions)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10--3.14-blue.svg)

A dependency-free Python and SQLite reference implementation for preventing delayed AI replies from restoring deleted conversation data.

## The problem

When a user deletes a conversation while a background worker is still generating a response, an unsafe persistence operation can restore unwanted data.

This project demonstrates a transactional approach to preventing that behavior.

## Features

- Transactional session validation.
- Rejection of delayed replies after session deletion.
- Atomic cascading deletion.
- Concurrent write and delete protection.
- Session isolation.
- Persistent SQLite storage.
- Unicode support.
- No external dependencies.

## How it works

Both reply persistence and session deletion use SQLite write transactions with BEGIN IMMEDIATE.

If deletion commits first, subsequent replies are rejected.

If saving commits first, deletion removes the saved replies through foreign-key cascading.

## Usage

Requires Python 3.10 or later.

```python
from late_reply_check import ReplyStore

store = ReplyStore("demo.sqlite3")

session = store.open_session()

assert store.save_reply(session, "First reply")

store.delete_session(session)

assert not store.save_reply(session, "Delayed reply")
assert store.replies(session) == []
```

## Testing

Run the complete test suite:

```bash
python -m unittest discover -v
```

## Verified CI results

| Python version | Tests | Result |
|---|---:|---|
| 3.10 | 16/16 | PASS |
| 3.11 | 16/16 | PASS |
| 3.12 | 16/16 | PASS |
| 3.13 | 16/16 | PASS |
| 3.14 | 16/16 | PASS |

Total: 80 successful test executions across five Python versions.

[Verified GitHub Actions run](https://github.com/etorkiyahya/late-reply-check/actions/runs/46031066638)

The test suite covers concurrent writes and deletion, independent processes, transaction rollback, foreign-key integrity, session isolation, Unicode handling, and persistence after reopening the database.

## Scope and limitations

This is an experimental reference implementation, not a production-ready security library.

Applications must implement authentication, authorization, cancellation, cache invalidation, and retention policies separately.

Session identifiers are not authentication credentials.

Logical deletion does not guarantee physical erasure from database pages, logs, replicas, or backups.

All writers must follow the same transactional rules. SQLite write contention may raise OperationalError. Callers must handle these errors appropriately.

Distributed database behavior is outside the current scope.

## Project status

Initial public implementation with automated regression testing.

External adoption and production deployment have not yet been established.

## Contributions

Reproducible bug reports, regression tests, and technical feedback are welcome.

See CONTRIBUTING.md and SECURITY.md.

## License

MIT License. See LICENSE.
## Integration example (FastAPI-like)

```python
from late_reply_check import ReplyStore

store = ReplyStore("app.sqlite3")

def handle_delete(session_id: str) -> None:
    store.delete_session(session_id)

def background_worker(session_id: str, reply: str) -> None:
    if not store.save_reply(session_id, reply):
        # Session was deleted; drop the reply silently.
        return
```
