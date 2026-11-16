"""Observation archive using the SDK1 storage format."""
import json
from geometry import encode_rings
from storage import atomic, version
from vendor.ring1 import Region

class Archive:
    def __init__(self, db):
        self.db = db
        self._check()

    def _check(self):
        if version(self.db) != 1:
            raise RuntimeError("unsupported archive storage version")

    def put(self, region_id, rings):
        self._check()
        if not isinstance(region_id, str) or not region_id:
            raise ValueError("nonempty region ID required")
        region = Region(rings)
        payload = json.dumps(encode_rings(region.rings), separators=(",", ":"))
        with atomic(self.db):
            row = self.db.execute("SELECT revision FROM regions1 WHERE region_id=?", (region_id,)).fetchone()
            revision = 1 if row is None else row[0] + 1
            self.db.execute("""INSERT INTO regions1 VALUES (?,?,?)
                ON CONFLICT(region_id) DO UPDATE SET
                revision=excluded.revision,rings_json=excluded.rings_json""",
                            (region_id, revision, payload))
        return revision

    def read(self, region_id):
        """Return the original closed ring sequences, with Fraction coordinates."""
        self._check()
        row = self.db.execute("SELECT rings_json FROM regions1 WHERE region_id=?", (region_id,)).fetchone()
        if row is None:
            raise KeyError(region_id)
        return Region(json.loads(row[0])).rings

    def revision(self, region_id):
        self._check()
        row = self.db.execute("SELECT revision FROM regions1 WHERE region_id=?", (region_id,)).fetchone()
        if row is None:
            raise KeyError(region_id)
        return row[0]

    def ids(self):
        self._check()
        return tuple(row[0] for row in self.db.execute("SELECT region_id FROM regions1 ORDER BY region_id"))
