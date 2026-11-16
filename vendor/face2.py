"""SDK2: exact simple faces only, independent of SDK1."""
import json
from fractions import Fraction
from geometry import (normalize_rings, edges, crossing, on_segment, rectangle,
                      point, parity_contains, segment_hits_window, encode_rings)
from storage import atomic

class Face:
    def __init__(self, vertices):
        ring, = normalize_rings([vertices])
        es = edges((ring,))
        for i, (a, b) in enumerate(es):
            for j in range(i + 1, len(es)):
                if j == i + 1 or (i == 0 and j == len(es) - 1):
                    continue
                c, d = es[j]
                if (crossing(a, b, c, d) is not None
                        or any(on_segment(p, c, d) for p in (a, b))
                        or any(on_segment(p, a, b) for p in (c, d))):
                    raise ValueError("SDK2 requires a simple face")
        self.vertices = ring
        if self.area() == 0:
            raise ValueError("zero area face")

    def contains(self, p):
        return parity_contains((self.vertices,), point(p))

    def boundary_touches(self, window):
        r = rectangle(window)
        return any(segment_hits_window(a, b, r) for a, b in edges((self.vertices,)))

    def area(self, window=None):
        poly = list(self.vertices[:-1])
        if window is not None:
            r = rectangle(window)
            for axis, bound, sign in ((0, r[0], 1), (0, r[2], -1),
                                      (1, r[1], 1), (1, r[3], -1)):
                if not poly:
                    break
                out = []
                a = poly[-1]
                for b in poly:
                    ain, bin_ = sign * (a[axis] - bound) >= 0, sign * (b[axis] - bound) >= 0
                    if ain != bin_:
                        t = (bound - a[axis]) / (b[axis] - a[axis])
                        out.append((a[0] + t * (b[0] - a[0]),
                                    a[1] + t * (b[1] - a[1])))
                    if bin_:
                        out.append(b)
                    a = b
                poly = out
        if len(poly) < 3:
            return Fraction(0)
        return abs(sum((a[0] * b[1] - a[1] * b[0]
                        for a, b in zip(poly, poly[1:] + poly[:1])), Fraction(0))) / 2

    def intersects(self, window):
        r = rectangle(window)
        return (self.boundary_touches(r) or self.area(r) > 0
                or self.contains(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)))

def install(db):
    """Install only the native face table; no observation or task mapping."""
    db.execute("""CREATE TABLE IF NOT EXISTS sdk2_faces (
        face_key TEXT PRIMARY KEY, vertices_json TEXT NOT NULL)""")

class FaceStore:
    """Native upsert/read/delete by face key; no observation identity semantics."""
    def __init__(self, db):
        self.db = db

    def put(self, key, vertices):
        if not isinstance(key, str) or not key:
            raise ValueError("nonempty face key required")
        face = Face(vertices)
        payload = json.dumps(encode_rings((face.vertices,))[0], separators=(",", ":"))
        with atomic(self.db):
            self.db.execute("""INSERT INTO sdk2_faces VALUES (?,?)
                ON CONFLICT(face_key) DO UPDATE SET vertices_json=excluded.vertices_json""",
                            (key, payload))

    def read(self, key):
        row = self.db.execute("SELECT vertices_json FROM sdk2_faces WHERE face_key=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return Face(json.loads(row[0]))

    def keys(self):
        return tuple(row[0] for row in self.db.execute("SELECT face_key FROM sdk2_faces ORDER BY face_key"))

    def delete(self, key):
        with atomic(self.db):
            self.db.execute("DELETE FROM sdk2_faces WHERE face_key=?", (key,))
