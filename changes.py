"""Exact open-set change components between two retained revisions.

The plane is cut into vertical slabs by every vertex x, every edge
intersection x and the window sides. Inside a slab the parity membership of
both revisions is constant on every horizontal line, so each connected
intersection of a change set with a slab is an open trapezoid (stored by its
open y-interval and exact area). Trapezoids of adjacent slabs are joined only
when their open y-intervals overlap in positive length: point or line contact
never creates such an overlap, so it can never connect two components.
"""
from fractions import Fraction
from geometry import edges, crossing, on_segment, parity_contains

def _strict_inside(rings, point):
    """Parity interior test that excludes any boundary point."""
    if any(on_segment(point, a, b) for a, b in edges(rings)):
        return False
    return parity_contains(rings, point)

def _y_at(a, b, x):
    return a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0])

def _subtract(intervals, lo, hi):
    """Open intervals of [lo, hi] not covered by the blocker intervals."""
    if lo >= hi:
        return []
    blockers = sorted((max(lo, a), min(hi, b)) for a, b in intervals
                      if max(lo, a) < min(hi, b))
    out, cursor = [], lo
    for a, b in blockers:
        if a > cursor:
            out.append((cursor, a))
        if b > cursor:
            cursor = b
    if cursor < hi:
        out.append((cursor, hi))
    return out

def _merge(intervals):
    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            if b > merged[-1][1]:
                merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged

def _clip_segment(a, b, window):
    """Liang-Barsky clip to the closed window; None when only point/empty."""
    xmin, ymin, xmax, ymax = window
    lo, hi = Fraction(0), Fraction(1)
    for axis in (0, 1):
        start, delta = a[axis], b[axis] - a[axis]
        lower, upper = window[axis], window[axis + 2]
        if delta == 0:
            if not lower <= start <= upper:
                return None
        else:
            t, u = (lower - start) / delta, (upper - start) / delta
            lo, hi = max(lo, min(t, u)), min(hi, max(t, u))
            if lo > hi:
                return None
    if lo == hi:
        return None
    return ((a[0] + lo * (b[0] - a[0]), a[1] + lo * (b[1] - a[1])),
            (a[0] + hi * (b[0] - a[0]), a[1] + hi * (b[1] - a[1])))

def _point_at(a, b, t):
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))

def _split_on_window(segments, window):
    """Split clipped segments wherever they meet a window boundary line.

    After this every segment touching a window side has an endpoint there,
    keeping cross-section parity correct in the slab next to the boundary.
    """
    xmin, ymin, xmax, ymax = window
    for a, b in segments:
        cuts = {Fraction(0), Fraction(1)}
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx:
            for x in (xmin, xmax):
                if min(a[0], b[0]) <= x <= max(a[0], b[0]):
                    cuts.add((x - a[0]) / dx)
        if dy:
            for y in (ymin, ymax):
                if min(a[1], b[1]) <= y <= max(a[1], b[1]):
                    cuts.add((y - a[1]) / dy)
        params = sorted(cuts)
        for t, u in zip(params, params[1:]):
            if t < u:
                yield _point_at(a, b, t), _point_at(a, b, u)

def _intervals(rings_edges, x, ymin, ymax, boundary_xs, rings):
    """Sorted open inside-y-intervals at x, restricted to the window span.

    Candidate cuts are the heights of every non-vertical edge crossing the
    section plus the endpoints of vertical edges on the slab boundaries
    (needed for slabs bounded only by vertical sides). Membership of each
    candidate interval is decided by an exact parity point test on the
    original rings, so clipped and vertical-only slabs stay exact.
    """
    cuts = {ymin, ymax}
    for a, b in rings_edges:
        if a[0] != b[0] and min(a[0], b[0]) < x < max(a[0], b[0]):
            cuts.add(_y_at(a, b, x))
        elif a[0] == b[0] and a[0] in boundary_xs:
            cuts.update((a[1], b[1]))
    ordered = sorted(c for c in cuts if ymin <= c <= ymax)
    out = []
    for lo, hi in zip(ordered, ordered[1:]):
        if lo >= hi:
            continue
        # Probe off-centre so a boundary passing through the exact midpoint
        # cannot be mistaken for interior membership.
        probe_y = (lo * 3 + hi) / 4
        if _strict_inside(rings, (x, probe_y)):
            out.append((lo, hi))
    return out

class _DSU:
    def __init__(self):
        self.parent = {}

    def add(self, item):
        self.parent.setdefault(item, item)

    def find(self, item):
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

def component_areas(old_rings, new_rings, window):
    """Gained/lost open connected-component areas inside an open window."""
    xmin, ymin, xmax, ymax = window
    if xmin == xmax or ymin == ymax:
        return (), ()
    # Clip every boundary edge to the closed window first: arrangement events
    # and cross-sections then never leave the window, while parity tests below
    # still use the original rings (closed-region semantics are unchanged).
    raw_a, raw_b = edges(old_rings), edges(new_rings)
    clipped_a = [s for s in (_clip_segment(a, b, window) for a, b in raw_a) if s]
    clipped_b = [s for s in (_clip_segment(a, b, window) for a, b in raw_b) if s]
    edges_a = tuple(_split_on_window(clipped_a, window))
    edges_b = tuple(_split_on_window(clipped_b, window))
    events = {xmin, xmax}
    for es in (edges_a, edges_b):
        for a, b in es:
            events.update((a[0], b[0]))
            if a[1] != b[1]:
                for y in (ymin, ymax):
                    t = (y - a[1]) / (b[1] - a[1])
                    if 0 <= t <= 1:
                        events.add(a[0] + t * (b[0] - a[0]))
    for pool in (edges_a, edges_b):
        for i, (a, b) in enumerate(pool):
            for c, d in pool[i + 1:]:
                p = crossing(a, b, c, d)
                if p is not None:
                    events.add(p[0])
    for a, b in edges_a:
        for c, d in edges_b:
            p = crossing(a, b, c, d)
            if p is not None:
                events.add(p[0])
    cuts = sorted(x for x in events if xmin <= x <= xmax)

    # Each trap: (index, (lo, hi), Fraction area); per slab, per change kind.
    traps = {"gained": [], "lost": []}
    dsu = {"gained": _DSU(), "lost": _DSU()}
    previous = {"gained": None, "lost": None}
    index = 0

    for left, right in zip(cuts, cuts[1:]):
        mid = (left + right) / 2
        # Vertical edges on either slab boundary contribute their endpoint
        # heights, which matters for slabs made only of vertical sides.
        inside_a = _intervals(edges_a, mid, ymin, ymax, (left, right), old_rings)
        inside_b = _intervals(edges_b, mid, ymin, ymax, (left, right), new_rings)
        blocked_a = _merge(inside_a)
        blocked_b = _merge(inside_b)
        width = right - left
        current = {"gained": [], "lost": []}
        # Gained = interior(B) minus closed A; lost = interior(A) minus closed B.
        for kind, inside, blocked in (
                ("gained", inside_b, blocked_a), ("lost", inside_a, blocked_b)):
            for base_lo, base_hi in inside:
                for part_lo, part_hi in _subtract(blocked, base_lo, base_hi):
                    area = width * (part_hi - part_lo)
                    token = (index, part_lo, part_hi)
                    index += 1
                    traps[kind].append((token, area))
                    dsu[kind].add(token)
                    current[kind].append((part_lo, part_hi, token))
        if left != xmin:
            # Connectivity across an event line is decided geometrically:
            # two traps join when their open y-intervals share a positive
            # length. A boundary cut point then splits components only when
            # it genuinely pinches the change set; point/line contact alone
            # never creates such an overlap.
            for kind in ("gained", "lost"):
                for lo_l, hi_l, token_l in previous[kind]:
                    for lo_r, hi_r, token_r in current[kind]:
                        if lo_l < hi_r and lo_r < hi_l:
                            dsu[kind].union(token_l, token_r)
        previous = current

    result = {}
    for kind in ("gained", "lost"):
        totals = {}
        for token, area in traps[kind]:
            root = dsu[kind].find(token)
            totals[root] = totals.get(root, Fraction(0)) + area
        result[kind] = tuple(sorted(a for a in totals.values() if a > 0))
    return result["gained"], result["lost"]
