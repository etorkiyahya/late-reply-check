"""Local SQLite reference implementation for rejecting stale replies.

Session IDs identify records; they are not authentication credentials.
"""
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path


class ReplyStore:
    def __init__(self, path):
        if str(path) == ":memory:":
            raise ValueError("Use a file-backed database; connections are separate")
        self.path = Path(path).expanduser().resolve()
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id)
                        ON DELETE CASCADE,
                    content TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS replies_session_id
                    ON replies(session_id, id);
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def open_session(self):
        session_id = uuid.uuid4().hex
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO sessions VALUES (?)", (session_id,))
        return session_id

    def save_reply(self, session_id, content):
        """Return False if the session was deleted; never recreate it."""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Reply must be nonempty text")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if active is None:
                return False
            db.execute(
                "INSERT INTO replies(session_id, content) VALUES (?, ?)",
                (session_id, content),
            )
        return True

    def delete_session(self, session_id):
        """Delete the session and its stored replies in one transaction."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return result.rowcount == 1

    def replies(self, session_id):
        with closing(self._connect()) as db:
            return [row[0] for row in db.execute(
                "SELECT content FROM replies WHERE session_id = ? ORDER BY id",
                (session_id,),
            )]
