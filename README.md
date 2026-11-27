# late-reply-check

Experimental Python/SQLite reference implementation for a chat persistence race:
a reply finishes after its conversation has been deleted.

## Problem

A background worker may retain a session identifier while a user deletes that
session. Saving the finished reply without checking the session can recreate
unwanted data.

## Approach

The reply writer and deletion operation use SQLite write transactions
(`BEGIN IMMEDIATE`). The writer checks that the session exists within its
transaction. The delete operation removes the session and its replies via a
foreign key cascade. If deletion commits first, a subsequent save is rejected;
if saving commits first, deletion removes that saved reply.

## Run

Python 3.10+ recommended; no third-party dependencies. Use a file-backed database; the implementation uses separate connections.

```sh
python -m unittest discover -v
```

## Example

```python
from late_reply_check import ReplyStore
from tempfile import TemporaryDirectory
from pathlib import Path

with TemporaryDirectory() as tmp:
    store = ReplyStore(Path(tmp) / "demo.sqlite3")
    session = store.open_session()
    assert store.save_reply(session, "first")
    store.delete_session(session)
    assert not store.save_reply(session, "late")
    assert store.replies(session) == []
```

## Scope and limitations

This is an independent, deliberately reduced demonstration derived from the
transactional approach tested in an earlier local regression. It does
not contain the private application, HTTP integration, recovery registry,
leases, or in-memory session cache. It is not a production security library.
Session identifiers are not authorization credentials. Applications must
implement authentication, authorization, request cancellation, cache invalidation,
and retention policies separately. Logical deletion does not imply physical
erasure of SQLite pages, logs, replicas or backups. All writers must follow the
same database invariants. Tests cover local SQLite behavior, not distributed
databases or every possible failure mode.

## Status

Initial experimental reference implementation; no claims about production deployment, external users or independent adoption. Feedback and reproducible bug reports are welcome. See CONTRIBUTING.md and SECURITY.md.

The test suite includes competing threads, a separate process, rollback, foreign-key integrity and restart checks. The GitHub Actions matrix is proposed; cloud results are not yet available. SQLite write contention can raise an OperationalError rather than return False; callers must handle errors. Never reuse old session identifiers or restore obsolete database backups as active state.

## License

MIT; see LICENSE.
