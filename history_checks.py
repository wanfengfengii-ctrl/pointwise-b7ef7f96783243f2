"""Public fixtures and smoke checks, separate from the unchanged original tests."""
import argparse
import json
import sqlite3
import tempfile
from fractions import Fraction as F
from pathlib import Path
from archive import Archive
from analysis import Analysis
from geometry import normalize_rings
from history_examples import CASES, FAR, box
from samples import build_legacy
from storage import create_legacy
from vendor.ring1 import Region

class BeforeCommit(RuntimeError):
    pass

class FailingConnection(sqlite3.Connection):
    """One-shot failure immediately before SQLite commit, never after commit."""
    def arm_commit_failure(self):
        self._fail_commit = True

    def commit(self):
        if getattr(self, "_fail_commit", False):
            self._fail_commit = False
            raise BeforeCommit("injected before commit")
        return super().commit()

def connection(path=":memory:"):
    db = sqlite3.connect(str(path), isolation_level=None, factory=FailingConnection)
    db.execute("PRAGMA foreign_keys=ON")
    return db

def snapshot(db):
    return tuple(db.iterdump())

def must_raise(kind, action):
    try:
        action()
    except kind:
        return
    raise AssertionError("expected " + kind.__name__)

def scaffold():
    # Only scalar consistency is checked here, not the claimed topology.
    for name, old, new, window, gained, lost in CASES:
        normalize_rings(old)
        normalize_rings(new)
        assert gained == tuple(sorted(gained)), name
        assert lost == tuple(sorted(lost)), name
        assert all(type(a) is F and a > 0 for a in gained + lost), name
        assert (sum(gained, F(0)) - sum(lost, F(0))
                == Region(new).area(window) - Region(old).area(window)), name
    db = connection()
    try:
        create_legacy(db)
        archive = Archive(db)
        archive.put("x", FAR)
        before = snapshot(db)
        db.arm_commit_failure()
        must_raise(BeforeCommit, lambda: archive.put("x", box(0, 0, 1, 1)))
        assert snapshot(db) == before
        assert not db.in_transaction
        assert archive.put("x", box(0, 0, 1, 1)) == 2
    finally:
        db.close()
    print("SCAFFOLD_OK: analytic area balances and pre-commit rollback fixture")

def check_result(actual, gained, lost):
    assert type(actual) is dict and set(actual) == {"gained", "lost"}, actual
    for key, expected in (("gained", gained), ("lost", lost)):
        values = actual[key]
        assert type(values) is tuple, actual
        assert all(type(a) is F and a > 0 for a in values), actual
        assert values == expected, (actual, gained, lost)

def geometry_checks():
    db = connection()
    try:
        create_legacy(db)
        archive = Archive(db)
        archive.enable_history()
        analysis = Analysis(archive)
        for name, old, new, window, gained, lost in CASES:
            # Both directions and reversed input orientations use the same contract.
            for suffix, a, b in (
                ("forward", old, new),
                ("reoriented", tuple(tuple(reversed(r)) for r in reversed(old)),
                 tuple(tuple(reversed(r)) for r in reversed(new)))):
                key = name + suffix
                r1 = archive.put(key, a)
                r2 = archive.put(key, b)
                check_result(analysis.changes(key, r1, r2, window), gained, lost)
                check_result(analysis.changes(key, r2, r1, window), lost, gained)
                check_result(analysis.changes(key, r1, r1, window), (), ())
        must_raise(KeyError, lambda: analysis.changes("absent", 1, 1, (0, 0, 1, 1)))
        must_raise(ValueError, lambda: analysis.changes(
            "equal_area_relocatedforward", 1, 2, (2, 0, 1, 1)))
    finally:
        db.close()

def history_roundtrip(path):
    db = connection(path)
    try:
        archive = build_legacy(db)
        archive.put("bow", box(0, 0, 1, 1))  # revision 1 was not retained
        before = snapshot(db)
        db.arm_commit_failure()
        must_raise(BeforeCommit, archive.enable_history)
        assert snapshot(db) == before and not db.in_transaction
        archive.enable_history()
        before = snapshot(db)
        archive.enable_history()
        assert snapshot(db) == before
        must_raise(KeyError, lambda: archive.read_revision("bow", 1))
        assert archive.read_revision("bow", 2) == normalize_rings(box(0, 0, 1, 1))
        before = snapshot(db)
        db.arm_commit_failure()
        must_raise(BeforeCommit, lambda: archive.put("bow", box(2, 0, 3, 1)))
        assert snapshot(db) == before and not db.in_transaction
        must_raise(KeyError, lambda: archive.read_revision("bow", 3))
        must_raise(ValueError, lambda: archive.put("bow", (((0, 0), (1, 0), (0, 0)),)))
        assert snapshot(db) == before
        assert archive.put("bow", box(2, 0, 3, 1)) == 3
        retained = archive.read_revision("bow", 3)
        assert archive.put("bow", box(4, 0, 5, 1)) == 4
        assert retained == normalize_rings(box(2, 0, 3, 1))
    finally:
        db.close()
    db = connection(path)
    try:
        archive = Archive(db)
        assert archive.revision("bow") == 4
        assert archive.read("bow") == normalize_rings(box(4, 0, 5, 1))
        must_raise(KeyError, lambda: archive.read_revision("bow", 1))
        must_raise(KeyError, lambda: archive.read_revision("bow", 5))
        must_raise(KeyError, lambda: archive.read_revision("missing", 1))
        assert archive.read_revision("bow", 2) == normalize_rings(box(0, 0, 1, 1))
        assert archive.read_revision("bow", 3) == retained
        result = Analysis(archive).changes("bow", 2, 3, (-1, -1, 6, 2))
        check_result(result, (F(1),), (F(1),))
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        print(json.dumps({"current_revision": 4, "compared_revisions": [2, 3],
                          "gained": list(map(str, result["gained"])),
                          "lost": list(map(str, result["lost"]))}, sort_keys=True))
    finally:
        db.close()

def verify():
    geometry_checks()
    with tempfile.TemporaryDirectory(prefix="history-check-") as directory:
        history_roundtrip(Path(directory) / "archive.sqlite")
    print("HISTORY_OK: directed patches and retained revision identity")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("scaffold", "verify", "demo"))
    command = parser.parse_args().command
    if command == "scaffold":
        scaffold()
    elif command == "verify":
        verify()
    else:
        with tempfile.TemporaryDirectory(prefix="history-demo-") as directory:
            history_roundtrip(Path(directory) / "archive.sqlite")

if __name__ == "__main__":
    main()
