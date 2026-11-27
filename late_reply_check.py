"""Transactional reference implementation for preventing late replies from restoring deleted sessions."""
from __future__ import annotations

import sqlite3
from pathlib import Path


class ReplyStore:
    """A SQLite-backed store that rejects replies for deleted sessions using BEGIN IMMEDIATE."""

    def __init__(self, path: str | Path) -> None:
        if str(path) == ":memory:":
            raise ValueError("In-memory databases are not supported for this reference implementation.")
        
        self._path = str(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    deleted INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )

    def open_session(self) -> str:
        """Create a new session and return its identifier."""
        session_id = f"sess-{id(object())}"
        with self._conn:
            self._conn.execute(
                "INSERT INTO sessions (id, deleted) VALUES (?, 0)", (session_id,)
            )
        return session_id

    def save_reply(self, session_id: str, body: str) -> bool:
        """Persist a reply. Return False if the session is deleted or missing."""
        if not isinstance(session_id, str):
            raise TypeError("session_id must be a string")

        with self._conn:  # BEGIN IMMEDIATE; commit or rollback
            cursor = self._conn.execute(
                "SELECT deleted FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()
            if row is None or row[0] == 1:
                return False  # Session deleted or never existed
            self._conn.execute(
                "INSERT INTO replies (session_id, body) VALUES (?, ?)",
                (session_id, body),
            )
        return True

    def delete_session(self, session_id: str) -> None:
        """Atomically mark a session deleted and cascade-remove its replies."""
        with self._conn:  # BEGIN IMMEDIATE; commit or rollback
            self._conn.execute(
                "UPDATE sessions SET deleted = 1 WHERE id = ?", (session_id,)
            )
            self._conn.execute(
                "DELETE FROM replies WHERE session_id = ?", (session_id,)
            )

    def replies(self, session_id: str) -> list[str]:
        """Return stored replies for a session (empty if deleted)."""
        cursor = self._conn.execute(
            "SELECT body FROM replies WHERE session_id = ? ORDER BY id", (session_id,)
        )
        return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def __enter__(self) -> "ReplyStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
