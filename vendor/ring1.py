"""SDK1: closed rings with even-odd fill. No simple-face export API."""
from fractions import Fraction
from itertools import combinations
from geometry import (normalize_rings, edges, crossing, rectangle, point,
                      parity_contains, segment_hits_window)

class Region:
    def __init__(self, rings):
        self.rings = normalize_rings(rings)
        self._edges = edges(self.rings)

    def contains(self, p):
        return parity_contains(self.rings, point(p))

    def boundary_touches(self, window):
        r = rectangle(window)
        return any(segment_hits_window(a, b, r) for a, b in self._edges)

    def area(self, window=None):
        """Integrate clipped odd cross-section lengths using exact rationals."""
        if window is None:
            xs = [p[0] for ring in self.rings for p in ring]
            ys = [p[1] for ring in self.rings for p in ring]
            r = min(xs), min(ys), max(xs), max(ys)
        else:
            r = rectangle(window)
        xmin, ymin, xmax, ymax = r
        if xmin == xmax or ymin == ymax:
            return Fraction(0)
        events = {xmin, xmax}
        for a, b in self._edges:
            events.update((a[0], b[0]))
            if a[1] != b[1]:
                for y in (ymin, ymax):
                    t = (y - a[1]) / (b[1] - a[1])
                    if 0 <= t <= 1:
                        events.add(a[0] + t * (b[0] - a[0]))
        for (a, b), (c, d) in combinations(self._edges, 2):
            p = crossing(a, b, c, d)
            if p is not None:
                events.add(p[0])
        cuts = sorted(x for x in events if xmin <= x <= xmax)

        def length(x):
            ys = sorted(a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0])
                        for a, b in self._edges
                        if min(a[0], b[0]) < x < max(a[0], b[0]))
            if len(ys) % 2:
                raise ArithmeticError("odd cross-section")
            return sum((max(Fraction(0), min(hi, ymax) - max(lo, ymin))
                        for lo, hi in zip(ys[::2], ys[1::2])), Fraction(0))

        return sum(((right - left) * (length((2 * left + right) / 3)
                     + length((left + 2 * right) / 3)) / 2
                    for left, right in zip(cuts, cuts[1:])), Fraction(0))

    def intersects(self, window):
        r = rectangle(window)
        return (self.boundary_touches(r) or self.area(r) > 0
                or self.contains(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)))
