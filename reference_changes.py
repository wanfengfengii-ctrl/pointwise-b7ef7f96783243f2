"""Independent cross-check reference for change component areas.

This deliberately uses a different decomposition than changes.py: horizontal
strips built from every vertex/intersection y after clipping to the window,
with exact parity membership sampled on the original rings. Two strip cells
are adjacent only when they share a positive-length open edge, so point/line
contact never joins them. It is a test oracle, not production code.
"""
from fractions import Fraction
from geometry import edges, crossing, parity_contains, on_segment


def _x_at(a, b, y):
    return a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])


def _clip_segment(a, b, window):
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


def _emit(row, cells, kind, j, k, p, q, lo, hi):
    if p >= q:
        return k
    token = (j, k)
    area = (q - p) * (hi - lo)
    row.append((token, p, q, kind, area))
    cells[kind][token] = area
    return k + 1


def _strict_inside(rings, point):
    """Interior test that excludes boundary points."""
    for a, b in edges(rings):
        if on_segment(point, a, b):
            return False
    return parity_contains(rings, point)


def _on_any(rings, point):
    return any(on_segment(point, a, b) for a, b in edges(rings))


def _inside_intervals(clipped, midy, rings, xmin, xmax):
    """Open x-intervals strictly inside the region on horizontal line midy.

    Non-vertical edges crossing the line give parity events in x; vertical
    edges and window-side exits give additional events. Candidate intervals
    are accepted only when a strictly interior probe confirms them, so
    boundary-only samples never count as area.
    """
    cuts = {xmin, xmax}
    for a, b in clipped:
        if a[1] != b[1] and min(a[1], b[1]) < midy < max(a[1], b[1]):
            cuts.add(_x_at(a, b, midy))
        if a[0] == b[0] and min(a[1], b[1]) <= midy <= max(a[1], b[1]):
            cuts.add(a[0])
        # A segment leaving through a window side bounds the in-window cell.
        dx = b[0] - a[0]
        if dx != 0:
            for x in (xmin, xmax):
                t = (x - a[0]) / dx
                if 0 <= t <= 1:
                    y = a[1] + t * (b[1] - a[1])
                    if min(a[1], b[1]) <= midy <= max(a[1], b[1]):
                        cuts.add(x)
    ordered = sorted(c for c in cuts if xmin <= c <= xmax)
    out = []
    for p, q in zip(ordered, ordered[1:]):
        if p >= q:
            continue
        probe = (p * 3 + q) / 4  # off-centre to avoid boundary midpoints
        if _strict_inside(rings, (probe, midy)):
            out.append((p, q))
    return out


def reference_components(old_rings, new_rings, window):
    xmin, ymin, xmax, ymax = window
    if xmin == xmax or ymin == ymax:
        return (), ()
    raw_clipped = [s for s in (
        _clip_segment(a, b, window)
        for a, b in edges(old_rings) + edges(new_rings)) if s]
    clipped = tuple(_split_on_window(raw_clipped, window))

    ycuts = {ymin, ymax}
    for a, b in clipped:
        ycuts.update((a[1], b[1]))
        # Intersections with the window's vertical sides split the strips so
        # a segment leaving through a side cannot inflate a neighbouring cell.
        dx = b[0] - a[0]
        if dx != 0:
            for x in (xmin, xmax):
                t = (x - a[0]) / dx
                if 0 <= t <= 1:
                    ycuts.add(a[1] + t * (b[1] - a[1]))
    for i, (a, b) in enumerate(clipped):
        for c, d in clipped[i + 1:]:
            p = crossing(a, b, c, d)
            if p is not None:
                ycuts.add(p[1])
    ys = sorted(y for y in ycuts if ymin <= y <= ymax)

    cells = {"gained": {}, "lost": {}}
    strips = []
    for j, (lo, hi) in enumerate(zip(ys, ys[1:])):
        if lo == hi:
            strips.append([])
            continue
        midy = (lo + hi) / 2
        inside_a = _inside_intervals(clipped, midy, old_rings, xmin, xmax)
        inside_b = _inside_intervals(clipped, midy, new_rings, xmin, xmax)
        row = []
        k = 0

        def add_cells(kind, base_intervals, blocked):
            nonlocal k
            for blo, bhi in base_intervals:
                cursor = blo
                for clo, chi in sorted(blocked):
                    clo, chi = max(clo, blo), min(chi, bhi)
                    if clo >= chi:
                        continue
                    if cursor < clo:
                        k = _emit(row, cells, kind, j, k, cursor, clo, lo, hi)
                    cursor = max(cursor, chi)
                if cursor < bhi:
                    k = _emit(row, cells, kind, j, k, cursor, bhi, lo, hi)

        add_cells("gained", inside_b, inside_a)
        add_cells("lost", inside_a, inside_b)
        row.sort(key=lambda item: item[1])
        strips.append(row)

    result = {}
    for kind in ("gained", "lost"):
        parent = {t: t for t in cells[kind]}

        def find(t):
            while parent[t] != t:
                parent[t] = parent[parent[t]]
                t = parent[t]
            return t

        def union(u, v):
            parent[find(v)] = find(u)

        for row in strips:
            kinded = [item for item in row if item[3] == kind]
            for left, right in zip(kinded, kinded[1:]):
                if left[2] == right[1]:
                    union(left[0], right[0])
        # Vertical neighbours join only through a genuine open channel on the
        # shared strip boundary: probe the boundary row itself, excluding all
        # boundary edges, so a single-point pinch (a butterfly waist) never
        # merges two lobes.
        grow_rings = new_rings if kind == "gained" else old_rings
        block_rings = old_rings if kind == "gained" else new_rings
        for boundary_y, upper, lower in zip(ys[1:-1], strips, strips[1:]):
            up = [item for item in upper if item[3] == kind]
            dn = [item for item in lower if item[3] == kind]
            xcuts = {xmin, xmax}
            for a, b in clipped:
                if not (min(a[1], b[1]) <= boundary_y <= max(a[1], b[1])):
                    continue
                if a[0] == b[0]:
                    xcuts.add(a[0])
                elif a[1] != b[1]:
                    xcuts.add(_x_at(a, b, boundary_y))
            xs = sorted(x for x in xcuts if xmin <= x <= xmax)
            for p, q in zip(xs, xs[1:]):
                if p >= q:
                    continue
                point = ((p * 3 + q) / 4, boundary_y)
                if not (_strict_inside(grow_rings, point)
                        and not _on_any(block_rings, point)
                        and not _strict_inside(block_rings, point)):
                    continue
                up_tokens = [item[0] for item in up
                             if item[1] < q and p < item[2]]
                dn_tokens = [item[0] for item in dn
                             if item[1] < q and p < item[2]]
                for token in up_tokens[1:]:
                    union(up_tokens[0], token)
                for token in dn_tokens[1:]:
                    union(dn_tokens[0], token)
                if up_tokens and dn_tokens:
                    union(up_tokens[0], dn_tokens[0])
        totals = {}
        for token, area in cells[kind].items():
            root = find(token)
            totals[root] = totals.get(root, Fraction(0)) + area
        result[kind] = tuple(sorted(a for a in totals.values() if a > 0))
    return result["gained"], result["lost"]
