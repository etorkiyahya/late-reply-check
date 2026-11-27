import sqlite3
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from late_reply_check import ReplyStore


class ReplyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.a = ReplyStore(self.path)
        self.b = ReplyStore(self.path)
        self.session = self.a.open_session()

    def test_active_session_accepts_reply(self):
        self.assertTrue(self.a.save_reply(self.session, "first"))
        self.assertEqual(self.b.replies(self.session), ["first"])

    def test_delete_before_save(self):
        self.assertTrue(self.b.delete_session(self.session))
        self.assertFalse(self.a.save_reply(self.session, "late"))
        self.assertEqual(self.a.replies(self.session), [])

    def test_save_before_delete(self):
        self.assertTrue(self.a.save_reply(self.session, "first"))
        self.assertTrue(self.b.delete_session(self.session))
        self.assertEqual(self.a.replies(self.session), [])

    def test_inflight_worker_rejected_after_delete(self):
        started, deleted = threading.Event(), threading.Event()
        outcome = []
        def worker():
            started.set()
            try:
                if not deleted.wait(5):
                    raise TimeoutError("Deletion signal not received")
                outcome.append(self.a.save_reply(self.session, "late"))
            except Exception as exc:
                outcome.append(exc)
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            self.assertTrue(started.wait(5))
            self.assertTrue(self.b.delete_session(self.session))
        finally:
            deleted.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, [False])
        self.assertEqual(self.a.replies(self.session), [])

    def test_new_session_isolated(self):
        self.b.delete_session(self.session)
        new_session = self.b.open_session()
        self.assertNotEqual(new_session, self.session)
        self.assertFalse(self.a.save_reply(self.session, "late"))
        self.assertEqual(self.b.replies(new_session), [])
        self.assertTrue(self.b.save_reply(new_session, "new"))

    def test_other_session_preserved(self):
        other = self.b.open_session()
        self.b.save_reply(other, "keep")
        self.a.delete_session(self.session)
        self.assertEqual(self.a.replies(other), ["keep"])

    def test_repeated_delete_and_unknown_session(self):
        self.assertTrue(self.a.delete_session(self.session))
        self.assertFalse(self.b.delete_session(self.session))
        self.assertFalse(self.a.save_reply("unknown", "late"))

    def test_invalid_reply_rejected(self):
        for value in ("", "  ", None, 123):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.a.save_reply(self.session, value)
        self.assertEqual(self.a.replies(self.session), [])

    def test_restart_does_not_restore_deleted_session(self):
        self.a.save_reply(self.session, "first")
        self.b.delete_session(self.session)
        reopened = ReplyStore(self.path)
        self.assertFalse(reopened.save_reply(self.session, "late"))
        self.assertEqual(reopened.replies(self.session), [])


    def test_concurrent_write_delete_race(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            for _ in range(30):
                session = self.a.open_session()
                barrier = threading.Barrier(2, timeout=5)
                def save():
                    barrier.wait()
                    return self.a.save_reply(session, "racing reply")
                def delete():
                    barrier.wait()
                    return self.b.delete_session(session)
                a, b = pool.submit(save), pool.submit(delete)
                self.assertIn(a.result(timeout=10), (True, False))
                self.assertTrue(b.result(timeout=10))
                self.assertEqual(self.a.replies(session), [])
                self.assertFalse(self.a.save_reply(session, "later"))

    def test_independent_process_rejects_late_reply(self):
        script = ("from late_reply_check import ReplyStore; import sys; "
                  "s=ReplyStore(sys.argv[1]); print('ready', flush=True); "
                  "input(); print(s.save_reply(sys.argv[2], 'late'), flush=True)")
        worker = subprocess.Popen(
            [sys.executable, '-c', script, str(self.path), self.session],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=Path(__file__).resolve().parent,
        )
        try:
            # Delete before allowing the other process to save. The worker
            # cannot save before receiving the newline on its stdin.
            self.assertTrue(self.b.delete_session(self.session))
            out, err = worker.communicate('\n', timeout=10)
            self.assertEqual(worker.returncode, 0, err)
            self.assertEqual(out.splitlines(), ['ready', 'False'])
            self.assertEqual(self.a.replies(self.session), [])
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.communicate()

    def test_failed_delete_rolls_back(self):
        self.a.save_reply(self.session, 'keep')
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TRIGGER stop_delete BEFORE DELETE ON sessions "
                       "BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.b.delete_session(self.session)
        self.assertEqual(self.a.replies(self.session), ['keep'])
        self.assertTrue(self.a.save_reply(self.session, 'still active'))

    def test_foreign_key_integrity(self):
        self.a.save_reply(self.session, 'old')
        self.b.delete_session(self.session)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM replies').fetchone()[0], 0)

    def test_unicode_and_literal_content(self):
        content = "مرحبا 🌍 'quoted'; --"
        self.assertTrue(self.a.save_reply(self.session, content))
        self.assertEqual(self.b.replies(self.session), [content])

    def test_memory_database_rejected(self):
        with self.assertRaises(ValueError):
            ReplyStore(':memory:')

    def test_relative_path_stays_bound(self):
        old = Path.cwd()
        try:
            os.chdir(self.path.parent)
            store = ReplyStore('test.sqlite3')
            os.chdir(old)
            self.assertTrue(store.save_reply(self.session, 'same file'))
            self.assertEqual(self.a.replies(self.session), ['same file'])
        finally:
            os.chdir(old)

if __name__ == "__main__":
    unittest.main()
