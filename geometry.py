"""Exact rational primitives shared by the two offline SDKs."""
from fractions import Fraction

def rational(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, Fraction)):
        raise ValueError("coordinates must be int, rational/decimal text, or Fraction")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("invalid rational coordinate") from exc

def point(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("point needs two coordinates")
    return tuple(map(rational, value))

def rectangle(value):
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("window needs xmin,ymin,xmax,ymax")
    r = tuple(map(rational, value))
    if r[0] > r[2] or r[1] > r[3]:
        raise ValueError("reversed window")
    return r

def sub(a, b):
    return a[0] - b[0], a[1] - b[1]

def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]

def on_segment(p, a, b):
    return (cross(sub(p, a), sub(b, a)) == 0
            and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))

def crossing(a, b, c, d):
    """Unique intersection, including endpoints; parallel lines return None."""
    u, v = sub(b, a), sub(d, c)
    det = cross(u, v)
    if not det:
        return None
    t, s = cross(sub(c, a), v) / det, cross(sub(c, a), u) / det
    if 0 <= t <= 1 and 0 <= s <= 1:
        return a[0] + t * u[0], a[1] + t * u[1]
    return None

def overlaps(a, b, c, d):
    if cross(sub(b, a), sub(d, c)) or cross(sub(c, a), sub(b, a)):
        return False
    axis = 0 if a[0] != b[0] else 1
    return max(min(a[axis], b[axis]), min(c[axis], d[axis])) < min(
        max(a[axis], b[axis]), max(c[axis], d[axis]))

def edges(rings):
    return tuple((a, b) for ring in rings for a, b in zip(ring, ring[1:]))

def normalize_rings(values):
    try:
        rings = tuple(tuple(point(p) for p in ring) for ring in values)
    except TypeError as exc:
        raise ValueError("rings must be sequences of points") from exc
    if not rings:
        raise ValueError("at least one ring required")
    for ring in rings:
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("rings must be explicitly closed with at least three edges")
    es = edges(rings)
    if any(a == b for a, b in es):
        raise ValueError("zero length edge")
    for i, (a, b) in enumerate(es):
        for c, d in es[i + 1:]:
            if overlaps(a, b, c, d):
                raise ValueError("collinear overlapping edges")
    return rings

def segment_hits_window(a, b, window):
    """Closed segment versus closed rectangle, including degenerate windows."""
    lo, hi = Fraction(0), Fraction(1)
    for axis in (0, 1):
        start, delta = a[axis], b[axis] - a[axis]
        lower, upper = window[axis], window[axis + 2]
        if delta == 0:
            if not lower <= start <= upper:
                return False
        else:
            t, u = (lower - start) / delta, (upper - start) / delta
            lo, hi = max(lo, min(t, u)), min(hi, max(t, u))
            if lo > hi:
                return False
    return True

def parity_contains(rings, p):
    """Closed even-odd region; works for crossing rings."""
    es = edges(rings)
    if any(on_segment(p, a, b) for a, b in es):
        return True
    x, y = p
    inside = False
    for a, b in es:
        if (a[1] > y) != (b[1] > y):
            hit = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < hit:
                inside = not inside
    return inside

def encode_rings(rings):
    return [[[str(x), str(y)] for x, y in ring] for ring in rings]
