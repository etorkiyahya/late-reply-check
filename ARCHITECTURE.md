# Architecture

## The race condition

A background worker generates a reply. Meanwhile, the user deletes the session.
Without transactional ordering, the reply write can commit **after** the delete,
resurrecting the session's replies.

## Why `BEGIN IMMEDIATE`

SQLite's default `DEFERRED` transactions acquire a write lock only at the first
write statement. Two concurrent connections can both read the session as "alive"
before either writes. `BEGIN IMMEDIATE` acquires the write lock **at transaction
start**, serializing the check-and-write sequence.

## Ordering guarantees

1. If `delete_session` commits first, any later `save_reply` sees `deleted = 1`
   and returns `False`.
2. If `save_reply` commits first, `delete_session` cascades and removes it via
   `ON DELETE CASCADE`.

## Scope

This is a reference implementation, not a distributed lock. SQLite serializes
writes per database file; applications with multiple databases must coordinate
externally.
