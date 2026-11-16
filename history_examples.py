"""Analytic inputs and expected areas; no change-analysis implementation."""
from fractions import Fraction as F
from samples import BUTTERFLY, DONUT

def box(x0, y0, x1, y1):
    return (((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)),)

FAR = box(10, 10, 11, 11)
# name, old rings, new rings, window, expected gained, expected lost
CASES = (
    ("equal_area_relocated", box(0, 0, 1, 1), box(2, 0, 3, 1),
     (-1, -1, 4, 2), (F(1),), (F(1),)),
    ("bow_point_contact", FAR, BUTTERFLY,
     (-1, -1, 3, 3), (F(1), F(1)), ()),
    ("fill_hole_shared_boundary", DONUT, box(4, 0, 8, 4),
     (3, -1, 9, 5), (F(4),), ()),
    ("partial_collinear_overlap", box(0, 0, 2, 2), box(1, 0, 3, 2),
     (-1, -1, 4, 3), (F(2),), (F(2),)),
    ("two_rings_point_contact", FAR, box(0, 0, 1, 1) + box(1, 1, 2, 2),
     (-1, -1, 3, 3), (F(1), F(1)), ()),
    ("auxiliary_cuts_are_not_boundaries", box(F(1, 2), 10, F(3, 2), 11),
     box(0, 0, 2, 2), (-1, -1, 3, 3), (F(4),), ()),
    ("window_removes_connecting_bar", FAR,
     (((0, 0), (3, 0), (3, 3), (2, 3), (2, 1),
       (1, 1), (1, 3), (0, 3), (0, 0)),),
     (0, 2, 3, 3), (F(1), F(1)), ()),
    ("rational_clipped_triangle", FAR,
     (((0, 0), (3, 0), (0, 3), (0, 0)),),
     (0, 0, 1, 3), (F(5, 2),), ()),
    ("identical_boundary", DONUT, DONUT, (3, -1, 9, 5), (), ()),
    ("line_window", FAR, BUTTERFLY, (1, -1, 1, 3), (), ()),
)
