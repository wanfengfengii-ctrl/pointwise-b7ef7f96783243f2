import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction as F
from archive import Archive
from analysis import Analysis, Hit
from samples import build_legacy, BUTTERFLY
from storage import connect, create_legacy, atomic, version
from vendor.face2 import FaceStore, install

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        self.archive = build_legacy(self.db)
        self.analysis = Analysis(self.archive)

    def tearDown(self):
        self.db.close()

    def test_complete_legacy_fixture(self):
        self.assertEqual(version(self.db), 1)
        self.assertEqual(self.archive.ids(), ("bow", "cross", "donut", "ell"))
        self.assertEqual(self.analysis.tasks(), ("hole", "lower", "survey", "upper"))
        self.assertEqual(self.analysis.run("upper"), (Hit("bow", F(1), True),))
        self.assertEqual(self.analysis.run("lower"), (Hit("bow", F(1), True),))
        self.assertEqual(self.analysis.run("hole"), (Hit("donut", F(0), True),))
        self.assertEqual(self.analysis.run("survey"), (
            Hit("bow", F(2), True), Hit("cross", F(14), True),
            Hit("donut", F(12), True), Hit("ell", F(5), True)))
        expected_tables = {"metadata", "regions1", "windows1"}
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, expected_tables)
        payload = self.db.execute("SELECT rings_json FROM regions1 WHERE region_id='bow'").fetchone()[0]
        self.assertEqual(json.loads(payload)[0][1], ["2", "2"])
        self.assertEqual(self.archive.read("bow"), BUTTERFLY)

    def test_unique_ids_zero_area_and_boundary(self):
        line = (1, F(1, 4), 1, F(1, 2))
        self.assertEqual(self.analysis.query(line, ("bow", "bow")), (Hit("bow", F(0), False),))
        window = (F(9, 10), F(1, 10), F(11, 10), F(1, 5))
        self.assertEqual(self.analysis.query(window, ("bow",)), (Hit("bow", F(1, 50), False),))
        self.assertEqual(self.analysis.query((1, 1, 1, 1), ("bow",)), (Hit("bow", F(0), True),))
        self.assertEqual(self.analysis.query((20, 20, 21, 21)), ())

    def test_saved_binding_and_existing_object_reads_replacement(self):
        self.analysis.save("fixed", (0, 0, 2, 2), ("bow", "bow"))
        self.analysis.save("empty", (0, 0, 2, 2), ())
        self.assertEqual(self.analysis.task("fixed")[1], ("bow",))
        self.assertEqual(self.archive.put("bow", (((0, 0), (4, 0), (4, 2), (0, 2), (0, 0)),)), 2)
        self.assertEqual(self.analysis.run("upper"), (Hit("bow", F(2), True),))
        self.assertEqual(self.analysis.run("fixed"), (Hit("bow", F(4), True),))
        self.archive.put("new", BUTTERFLY)
        self.assertEqual(self.analysis.task("survey")[1], ("bow", "cross", "donut", "ell"))
        self.assertEqual(self.analysis.run("empty"), ())
        self.analysis.save("fixed", (0, 0, 1, 1), ("new",))
        self.assertEqual(self.analysis.run("fixed"), (Hit("new", F(1, 2), True),))

    def test_failed_inputs_preserve_business_state(self):
        original = self.archive.read("bow")
        with self.assertRaises(ValueError):
            self.archive.put("bow", (((0, 0), (1, 0), (0, 0)),))
        self.assertEqual(self.archive.read("bow"), original)
        self.assertEqual(self.archive.revision("bow"), 1)
        for action in (lambda: self.archive.read("missing"),
                       lambda: self.analysis.run("missing"),
                       lambda: self.analysis.save("upper", (0, 0, 1, 1), ("missing",))):
            with self.assertRaises(KeyError):
                action()
        with self.assertRaises(ValueError):
            self.analysis.query((2, 0, 1, 1))
        with self.assertRaises(ValueError):
            self.analysis.query((0, 0, 1, 1), "bow")
        self.assertEqual(self.analysis.run("upper"), (Hit("bow", F(1), True),))

    def test_atomic_ddl_dml_and_hook(self):
        def fail():
            raise RuntimeError("before commit")
        with self.assertRaisesRegex(RuntimeError, "before commit"):
            with atomic(self.db, before_commit=fail):
                self.db.execute("CREATE TABLE trial (value INTEGER)")
                self.db.execute("UPDATE metadata SET value='2' WHERE key='storage_version'")
                self.db.execute("DELETE FROM windows1")
        self.assertEqual(version(self.db), 1)
        self.assertEqual(len(self.analysis.tasks()), 4)
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='trial'").fetchone())
        self.assertFalse(self.db.in_transaction)
        with atomic(self.db):
            self.db.execute("CREATE TABLE trial (value INTEGER)")
        with self.assertRaises(RuntimeError):
            with atomic(self.db):
                with atomic(self.db):
                    pass
        self.assertFalse(self.db.in_transaction)

class NativeFaceStoreTests(unittest.TestCase):
    def test_native_roundtrip_replacement_and_rejection(self):
        db = connect(":memory:")
        try:
            install(db)
            store = FaceStore(db)
            store.put("f", ((0, 0), (2, 0), (0, 2), (0, 0)))
            self.assertEqual(store.read("f").area(), 2)
            store.put("f", ((0, 0), (3, 0), (0, 2), (0, 0)))
            self.assertEqual(store.read("f").area(), 3)
            with self.assertRaises(ValueError):
                store.put("f", BUTTERFLY[0])
            self.assertEqual(store.read("f").area(), 3)
            self.assertEqual(store.keys(), ("f",))
            store.delete("f")
            self.assertEqual(store.keys(), ())
            with self.assertRaises(KeyError):
                store.read("f")
        finally:
            db.close()

class FilePersistenceTests(unittest.TestCase):
    def test_reopen_complete_old_database_and_continue(self):
        with tempfile.TemporaryDirectory(prefix="ring-test-") as directory:
            path = Path(directory) / "old.sqlite"
            db = connect(path)
            try:
                archive = build_legacy(db)
                expected = Analysis(archive).run("survey")
            finally:
                db.close()
            db = connect(path)
            try:
                archive = Archive(db)
                analysis = Analysis(archive)
                self.assertEqual(analysis.run("survey"), expected)
                archive.put("bow", (((0, 0), (3, 0), (0, 2), (0, 0)),))
                self.assertEqual(archive.revision("bow"), 2)
                self.assertEqual(analysis.query((-1, -1, 4, 4), ("bow",)), (Hit("bow", F(3), True),))
                def fail():
                    raise RuntimeError("stop")
                with self.assertRaises(RuntimeError):
                    with atomic(db, before_commit=fail):
                        db.execute("DELETE FROM regions1")
                        db.execute("DELETE FROM windows1")
            finally:
                db.close()
            db = connect(path)
            try:
                archive = Archive(db)
                self.assertEqual(archive.revision("bow"), 2)
                self.assertEqual(Analysis(archive).run("lower"), (Hit("bow", F(23, 12), True),))
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))
            finally:
                db.close()
