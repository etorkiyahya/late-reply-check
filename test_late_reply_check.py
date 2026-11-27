import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from late_reply_check import ReplyStore


class TestLateReplyCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite3"
        self.store = ReplyStore(self.path)
        self.session = self.store.open_session()

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_memory_database_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ReplyStore(":memory:")

    def test_save_and_retrieve(self) -> None:
        self.assertTrue(self.store.save_reply(self.session, "hello"))
        self.assertEqual(self.store.replies(self.session), ["hello"])

    def test_reject_reply_after_deletion(self) -> None:
        self.store.delete_session(self.session)
        self.assertFalse(self.store.save_reply(self.session, "late"))
        self.assertEqual(self.store.replies(self.session), [])

    def test_literal_content(self) -> None:
        content = "مرحبا \U0001F680 'quoted'; --\""
        self.assertTrue(self.store.save_reply(self.session, content))
        self.assertEqual(self.store.replies(self.session), [content])

    def test_integrity(self) -> None:
        self.store.save_reply(self.session, "old")
        self.store.delete_session(self.session)
        with self.store._conn as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM replies').fetchone()[0], 0)

    def test_relative_path_stays_bound(self) -> None:
        old = Path.cwd()
        try:
            os.chdir(self.path.parent)
            store = ReplyStore('test.sqlite3')
            os.chdir(old)
            self.assertTrue(store.save_reply(self.session, 'same file'))
            self.assertEqual(store.replies(self.session), ['same file'])
            store.close()
        finally:
            os.chdir(old)

    def test_transaction_rolls_back(self) -> None:
        self.store.save_reply(self.session, 'keep')
        with self.store._conn as db:
            db.execute("CREATE TRIGGER stop_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
        with self.assertRaises(Exception):
            self.store.delete_session(self.session)
        self.assertEqual(self.store.replies(self.session), ['keep'])
        self.assertTrue(self.store.save_reply(self.session, 'still active'))

    def test_stress_concurrent_writes_and_deletes(self) -> None:
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for _ in range(50):
                    self.store.save_reply(self.session, "late")
            except Exception as exc:
                errors.append(exc)

        def deleter() -> None:
            try:
                time.sleep(0.01)
                self.store.delete_session(self.session)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(2)]
        threads.append(threading.Thread(target=deleter))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertFalse(errors)
        self.assertEqual(self.store.replies(self.session), [])

    def test_persistence_after_reopen(self) -> None:
        self.store.save_reply(self.session, "hello")
        self.store.delete_session(self.session)
        self.store.close()

        store2 = ReplyStore(self.path)
        self.assertEqual(store2.replies(self.session), [])
        cursor = store2._conn.execute("SELECT deleted FROM sessions WHERE id = ?", (self.session,))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)
        store2.close()

    def test_sqlite_busy_timeout(self) -> None:
        def slow_writer() -> None:
            with self.store._conn:
                self.store._conn.execute("SELECT 1")
                time.sleep(0.1)
                self.store._conn.execute(
                    "INSERT INTO replies (session_id, body) VALUES (?, ?)",
                    (self.session, "slow"),
                )

        t = threading.Thread(target=slow_writer)
        t.start()
        time.sleep(0.01)
        result = self.store.save_reply(self.session, "fast")
        t.join()
        self.assertTrue(result)
        self.assertIn("slow", self.store.replies(self.session))


if __name__ == "__main__":
    unittest.main()
