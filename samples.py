"""Finite legacy fixture and a complete old-database builder."""
from archive import Archive
from analysis import Analysis
from storage import create_legacy

BUTTERFLY = (((0, 0), (2, 2), (0, 2), (2, 0), (0, 0)),)
DONUT = (
    ((4, 0), (8, 0), (8, 4), (4, 4), (4, 0)),
    ((5, 1), (7, 1), (7, 3), (5, 3), (5, 1)),
)
CROSSING = (
    ((0, 0), (3, 0), (3, 3), (0, 3), (0, 0)),
    ((2, 1), (5, 1), (5, 4), (2, 4), (2, 1)),
)
L_SHAPE = (((10, 0), (13, 0), (13, 1), (11, 1), (11, 3), (10, 3), (10, 0)),)

def build_legacy(db):
    create_legacy(db)
    archive = Archive(db)
    for region_id, rings in (("bow", BUTTERFLY), ("donut", DONUT),
                              ("cross", CROSSING), ("ell", L_SHAPE)):
        archive.put(region_id, rings)
    analysis = Analysis(archive)
    analysis.save("upper", (0, 1, 2, 2), ("bow",))
    analysis.save("lower", (0, 0, 2, 1), ("bow",))
    analysis.save("hole", (5, 1, 7, 3), ("donut",))
    analysis.save("survey", (-1, -1, 14, 5))
    return archive
