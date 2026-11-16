"""Live window analysis and durable, identity-bound window jobs."""
import json
from dataclasses import dataclass
from fractions import Fraction
from changes import component_areas
from geometry import rectangle
from storage import atomic
from vendor.ring1 import Region

@dataclass(frozen=True)
class Hit:
    region_id: str
    area: Fraction
    boundary: bool

class Analysis:
    def __init__(self, archive):
        self.archive = archive

    def _ids(self, region_ids):
        available = self.archive.ids()
        if region_ids is None:
            return available
        if isinstance(region_ids, (str, bytes)):
            raise ValueError("IDs must be a sequence")
        wanted = tuple(region_ids)
        if any(not isinstance(item, str) or not item for item in wanted):
            raise ValueError("invalid region ID")
        missing = set(wanted) - set(available)
        if missing:
            raise KeyError(sorted(missing)[0])
        return tuple(sorted(set(wanted)))

    def query(self, window, region_ids=None):
        """Return one sorted Hit per region whose closed region meets window."""
        r = rectangle(window)
        hits = []
        for region_id in self._ids(region_ids):
            region = Region(self.archive.read(region_id))
            if region.intersects(r):
                hits.append(Hit(region_id, region.area(r), region.boundary_touches(r)))
        return tuple(hits)

    def changes(self, region_id, old_revision, new_revision, window):
        """Open-set gained/lost component areas between two retained revisions."""
        r = rectangle(window)
        # Missing region or any not-retained revision raises KeyError; the
        # window is validated first, matching the original query conventions.
        old_rings = self.archive.read_revision(region_id, old_revision)
        new_rings = self.archive.read_revision(region_id, new_revision)
        if old_revision == new_revision:
            return {"gained": (), "lost": ()}
        gained, lost = component_areas(old_rings, new_rings, r)
        return {"gained": gained, "lost": lost}

    def save(self, name, window, region_ids=None):
        """Bind a closed window and current IDs, not a copy of their geometry."""
        if not isinstance(name, str) or not name:
            raise ValueError("nonempty job name required")
        r, ids = rectangle(window), self._ids(region_ids)
        with atomic(self.archive.db):
            self.archive.db.execute("""INSERT INTO windows1 VALUES (?,?,?)
                ON CONFLICT(name) DO UPDATE SET
                window_json=excluded.window_json,ids_json=excluded.ids_json""",
                (name, json.dumps(list(map(str, r))), json.dumps(ids)))

    def task(self, name):
        self.archive._check()
        row = self.archive.db.execute(
            "SELECT window_json,ids_json FROM windows1 WHERE name=?", (name,)).fetchone()
        if row is None:
            raise KeyError(name)
        return rectangle(json.loads(row[0])), tuple(json.loads(row[1]))

    def run(self, name):
        window, ids = self.task(name)
        return self.query(window, ids)

    def tasks(self):
        self.archive._check()
        return tuple(row[0] for row in self.archive.db.execute("SELECT name FROM windows1 ORDER BY name"))
