"""Observation archive using the SDK1 storage format, with optional history."""
import json
from geometry import encode_rings, normalize_rings
from storage import atomic, version
from vendor.ring1 import Region

HISTORY_KEY = "history_enabled"
HISTORY_TABLE = "region_history"

class Archive:
    def __init__(self, db):
        self.db = db
        self._check()

    def _check(self):
        if version(self.db) != 1:
            raise RuntimeError("unsupported archive storage version")

    def _history_on(self):
        row = self.db.execute(
            "SELECT value FROM metadata WHERE key=?", (HISTORY_KEY,)).fetchone()
        return row is not None and row[0] == "1"

    def enable_history(self):
        """Atomically turn on retention and snapshot every current revision.

        Idempotent: a second call changes nothing. Revisions overwritten before
        history was enabled are not reconstructed.
        """
        self._check()
        if self._history_on():
            return None
        with atomic(self.db):
            self.db.execute(f"""CREATE TABLE {HISTORY_TABLE} (
                region_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
                rings_json TEXT NOT NULL,
                PRIMARY KEY (region_id, revision))""")
            self.db.execute(
                "INSERT INTO metadata VALUES (?, '1')", (HISTORY_KEY,))
            current = self.db.execute(
                "SELECT region_id, revision, rings_json FROM regions1").fetchall()
            self.db.executemany(
                f"INSERT INTO {HISTORY_TABLE} VALUES (?,?,?)", current)
        return None

    def put(self, region_id, rings):
        self._check()
        if not isinstance(region_id, str) or not region_id:
            raise ValueError("nonempty region ID required")
        # Geometry validation happens before any write, so failures cannot
        # consume a revision number or touch history/enabled state.
        region = Region(rings)
        payload = json.dumps(encode_rings(region.rings), separators=(",", ":"))
        retain = self._history_on()
        with atomic(self.db):
            row = self.db.execute("SELECT revision FROM regions1 WHERE region_id=?", (region_id,)).fetchone()
            revision = 1 if row is None else row[0] + 1
            self.db.execute("""INSERT INTO regions1 VALUES (?,?,?)
                ON CONFLICT(region_id) DO UPDATE SET
                revision=excluded.revision,rings_json=excluded.rings_json""",
                            (region_id, revision, payload))
            if retain:
                self.db.execute(
                    f"INSERT INTO {HISTORY_TABLE} VALUES (?,?,?)",
                    (region_id, revision, payload))
        return revision

    def read(self, region_id):
        """Return the original closed ring sequences, with Fraction coordinates."""
        self._check()
        row = self.db.execute("SELECT rings_json FROM regions1 WHERE region_id=?", (region_id,)).fetchone()
        if row is None:
            raise KeyError(region_id)
        return Region(json.loads(row[0])).rings

    def read_revision(self, region_id, revision):
        """Return an independent copy of one retained revision's raw rings."""
        self._check()
        if not self.db.execute(
                "SELECT 1 FROM regions1 WHERE region_id=?", (region_id,)).fetchone():
            raise KeyError(region_id)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision <= 0:
            raise KeyError(revision)
        row = self.db.execute(
            f"SELECT rings_json FROM {HISTORY_TABLE} WHERE region_id=? AND revision=?",
            (region_id, revision)).fetchone() if self._history_on() else None
        if row is None:
            raise KeyError(revision)
        # A freshly normalized copy: callers can neither mutate the archive
        # nor observe later puts through a previously returned value.
        return normalize_rings(json.loads(row[0]))

    def revision(self, region_id):
        self._check()
        row = self.db.execute("SELECT revision FROM regions1 WHERE region_id=?", (region_id,)).fetchone()
        if row is None:
            raise KeyError(region_id)
        return row[0]

    def ids(self):
        self._check()
        return tuple(row[0] for row in self.db.execute("SELECT region_id FROM regions1 ORDER BY region_id"))
