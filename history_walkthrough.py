"""Small standalone walk-through of history retention and change analysis.

Run directly:  python3 -B history_walkthrough.py

It uses only an in-memory SQLite database and prints every step, so it can be
read top to bottom as a compact reference for the three new entry points.
"""
from fractions import Fraction as F

from archive import Archive
from analysis import Analysis
from storage import connect, create_legacy
from history_examples import box


def main():
    db = connect(":memory:")
    create_legacy(db)
    archive = Archive(db)
    analysis = Analysis(archive)

    # Revision 1 is overwritten before history is enabled, so it is lost.
    archive.put("zone", box(0, 0, 1, 1))
    archive.put("zone", box(0, 0, 2, 2))  # revision 2, still pre-history
    archive.enable_history()
    # Idempotent: a second call changes nothing.
    archive.enable_history()

    r3 = archive.put("zone", box(2, 0, 3, 1))
    r4 = archive.put("zone", box(2, 0, 3, 2))
    r5 = archive.put("zone", box(4, 0, 5, 1))

    # Pre-enable revisions are not reconstructed.
    for lost_revision in (1, 2):
        try:
            archive.read_revision("zone", lost_revision)
        except KeyError:
            print("revision", lost_revision, "was not retained (pre-history)")

    # Each retained revision returns an independent raw ring copy.
    print("revision", r3, "first vertex:",
          archive.read_revision("zone", r3)[0][0])
    print("revision", r4, "first vertex:",
          archive.read_revision("zone", r4)[0][0])

    # Equal total area (1) but relocated: one gained and one lost patch.
    relocated = analysis.changes("zone", r3, r5, (-1, -1, 6, 3))
    print("relocated comparison:", relocated)
    assert relocated == {"gained": (F(1),), "lost": (F(1),)}

    # Growing the region reports only gained area.
    grown = analysis.changes("zone", r3, r4, (-1, -1, 4, 3))
    print("growth comparison:", grown)
    assert grown == {"gained": (F(1),), "lost": ()}

    # A point/line window has no two-dimensional interior: always empty.
    degenerate = analysis.changes("zone", r3, r4, (1, 0, 1, 2))
    print("line window:", degenerate)
    assert degenerate == {"gained": (), "lost": ()}

    # Comparing a revision with itself is empty (but it must still exist).
    same = analysis.changes("zone", r4, r4, (-1, -1, 4, 3))
    print("same revision:", same)
    assert same == {"gained": (), "lost": ()}
    db.close()
    print("WALKTHROUGH_OK")


if __name__ == "__main__":
    main()
