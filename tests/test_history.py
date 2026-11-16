"""Independent regression for history retention and open-set change patches.

These tests are written separately from the provided history_checks fixtures.
The geometry oracle cross-checks the vertical-slab engine against an
independent horizontal-strip implementation in reference_changes.py.
"""
import json
import tempfile
import unittest
from fractions import Fraction as F
from pathlib import Path

from archive import Archive, HISTORY_TABLE, HISTORY_KEY
from analysis import Analysis
from changes import component_areas
from reference_changes import reference_components
from storage import connect, create_legacy, atomic
from history_examples import box, CASES
from samples import BUTTERFLY, DONUT


def fresh():
    db = connect(":memory:")
    create_legacy(db)
    return db, Archive(db)


def triangle(x0=0):
    return (((x0, 0), (x0 + 3, 0), (x0, 3), (x0, 0)),)


class RetentionTests(unittest.TestCase):
    def test_enable_snapshots_current_and_is_idempotent(self):
        db, archive = fresh()
        r1 = archive.put("z", box(0, 0, 1, 1))
        r2 = archive.put("z", box(0, 0, 2, 2))
        archive.enable_history()
        # Pre-enable revision 1 is never reconstructed.
        with self.assertRaises(KeyError):
            archive.read_revision("z", 1)
        self.assertEqual(archive.read_revision("z", r2),
                         tuple(tuple(tuple(p) for p in ring)
                               for ring in box(0, 0, 2, 2)))
        before = list(db.iterdump())
        archive.enable_history()
        archive.enable_history()
        self.assertEqual(list(db.iterdump()), before)
        db.close()

    def test_empty_archive_enables_history(self):
        db, archive = fresh()
        archive.enable_history()
        self.assertEqual(archive.ids(), ())
        r = archive.put("solo", box(0, 0, 1, 1))
        self.assertEqual(archive.read_revision("solo", r),
                         tuple(tuple(tuple(p) for p in ring)
                               for ring in box(0, 0, 1, 1)))
        db.close()

    def test_put_without_history_keeps_legacy_behavior(self):
        db, archive = fresh()
        archive.put("z", box(0, 0, 1, 1))
        archive.put("z", box(0, 0, 2, 2))
        self.assertFalse(db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (HISTORY_TABLE,)).fetchone())
        with self.assertRaises(KeyError):
            archive.read_revision("z", 1)
        db.close()

    def test_revision_numbers_advance_and_history_tracks_each(self):
        db, archive = fresh()
        archive.enable_history()
        r1 = archive.put("z", box(0, 0, 1, 1))
        r2 = archive.put("z", box(2, 0, 3, 1))
        r3 = archive.put("z", box(4, 0, 5, 1))
        self.assertEqual((r1, r2, r3), (1, 2, 3))
        for rev, x0 in ((1, 0), (2, 2), (3, 4)):
            rings = archive.read_revision("z", rev)
            self.assertEqual(rings[0][0], (F(x0), F(0)))
        db.close()

    def test_returned_revision_is_independent(self):
        db, archive = fresh()
        archive.enable_history()
        r = archive.put("z", box(0, 0, 1, 1))
        first = archive.read_revision("z", r)
        archive.put("z", box(9, 9, 10, 10))
        second = archive.read_revision("z", r)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(archive.read("z")[0][0], (F(9), F(9)))
        db.close()

    def test_missing_region_and_revision_key_errors(self):
        db, archive = fresh()
        archive.enable_history()
        archive.put("z", box(0, 0, 1, 1))
        with self.assertRaises(KeyError):
            archive.read_revision("ghost", 1)
        with self.assertRaises(KeyError):
            archive.read_revision("z", 7)
        with self.assertRaises(KeyError):
            archive.read_revision("z", 0)
        db.close()

    def test_failed_put_consumes_no_revision_and_preserves_history(self):
        db, archive = fresh()
        archive.enable_history()
        r1 = archive.put("z", box(0, 0, 1, 1))
        good = archive.read_revision("z", r1)
        with self.assertRaises(ValueError):
            archive.put("z", (((0, 0), (1, 0), (0, 0)),))
        self.assertEqual(archive.revision("z"), 1)
        self.assertEqual(archive.read("z"), good)
        # The failed put did not insert a history row nor burn number 2.
        self.assertEqual(archive.put("z", box(0, 0, 2, 2)), 2)
        self.assertEqual(archive.read_revision("z", 1), good)
        db.close()

    def test_pre_commit_failure_rolls_back_everything(self):
        db, archive = fresh()
        archive.enable_history()
        archive.put("z", box(0, 0, 1, 1))
        before = list(db.iterdump())
        def fail():
            raise RuntimeError("stop")
        with self.assertRaises(RuntimeError):
            with atomic(db, before_commit=fail):
                db.execute("INSERT INTO regions1 VALUES ('q', 1, '[]')")
                db.execute(f"INSERT INTO {HISTORY_TABLE} VALUES ('q', 1, '[]')")
        self.assertEqual(list(db.iterdump()), before)
        self.assertFalse(db.in_transaction)
        db.close()

    def test_reopen_preserves_history_and_enabled_state(self):
        with tempfile.TemporaryDirectory(prefix="hist-") as directory:
            path = Path(directory) / "a.sqlite"
            db = connect(path)
            create_legacy(db)
            archive = Archive(db)
            archive.enable_history()
            r1 = archive.put("z", box(0, 0, 1, 1))
            r2 = archive.put("z", box(2, 0, 3, 1))
            db.close()
            db = connect(path)
            archive = Archive(db)
            self.assertTrue(db.execute(
                "SELECT value FROM metadata WHERE key=?",
                (HISTORY_KEY,)).fetchone())
            self.assertEqual(archive.read_revision("z", r1)[0][0], (F(0), F(0)))
            self.assertEqual(archive.read_revision("z", r2)[0][0], (F(2), F(0)))
            # History stays enabled after reopen.
            r3 = archive.put("z", box(4, 0, 5, 1))
            self.assertEqual(archive.read_revision("z", r3)[0][0], (F(4), F(0)))
            db.close()


class ChangeSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.db, self.archive = fresh()
        self.archive.enable_history()
        self.analysis = Analysis(self.archive)

    def tearDown(self):
        self.db.close()

    def _put_pair(self, name, old, new):
        r1 = self.archive.put(name, old)
        r2 = self.archive.put(name, new)
        return r1, r2

    def test_equal_area_relocation_gives_separate_patches(self):
        r1, r2 = self._put_pair("p", box(0, 0, 1, 1), box(2, 0, 3, 1))
        out = self.analysis.changes("p", r1, r2, (-1, -1, 4, 2))
        self.assertEqual(out, {"gained": (F(1),), "lost": (F(1),)})
        # Reverse comparison swaps the directions.
        rev = self.analysis.changes("p", r2, r1, (-1, -1, 4, 2))
        self.assertEqual(rev, {"gained": (F(1),), "lost": (F(1),)})

    def test_same_revision_is_empty_but_must_exist(self):
        r1, _ = self._put_pair("p", box(0, 0, 1, 1), box(2, 0, 3, 1))
        self.assertEqual(self.analysis.changes("p", r1, r1, (-1, -1, 4, 2)),
                         {"gained": (), "lost": ()})
        with self.assertRaises(KeyError):
            self.analysis.changes("p", 1, 99, (-1, -1, 4, 2))
        with self.assertRaises(KeyError):
            self.analysis.changes("nope", 1, 1, (-1, -1, 4, 2))

    def test_degenerate_windows_are_empty(self):
        r1, r2 = self._put_pair("p", box(0, 0, 1, 1), box(2, 0, 3, 1))
        for w in ((1, 0, 1, 2), (0, 1, 3, 1), (1, 1, 1, 1)):
            self.assertEqual(self.analysis.changes("p", r1, r2, w),
                             {"gained": (), "lost": ()})
        with self.assertRaises(ValueError):
            self.analysis.changes("p", r1, r2, (2, 0, 1, 1))

    def test_duplicate_component_areas_are_kept_not_deduped(self):
        # Two equal-area gained lobes touching only at a point.
        new = box(0, 0, 1, 1) + box(1, 1, 2, 2)
        r1, r2 = self._put_pair("p", box(10, 10, 11, 11), new)
        out = self.analysis.changes("p", r1, r2, (-1, -1, 3, 3))
        self.assertEqual(out["gained"], (F(1), F(1)))
        self.assertEqual(out["lost"], ())

    def test_self_intersecting_butterfly_splits_into_two_lobes(self):
        r1, r2 = self._put_pair("p", box(10, 10, 11, 11), BUTTERFLY)
        out = self.analysis.changes("p", r1, r2, (-1, -1, 3, 3))
        self.assertEqual(out, {"gained": (F(1), F(1)), "lost": ()})

    def test_hole_fill_is_one_patch(self):
        r1, r2 = self._put_pair("p", DONUT, box(4, 0, 8, 4))
        out = self.analysis.changes("p", r1, r2, (3, -1, 9, 5))
        self.assertEqual(out, {"gained": (F(4),), "lost": ()})

    def test_hole_creation_reports_lost_ring(self):
        r1, r2 = self._put_pair("p", box(4, 0, 8, 4), DONUT)
        out = self.analysis.changes("p", r1, r2, (3, -1, 9, 5))
        self.assertEqual(out, {"gained": (), "lost": (F(4),)})

    def test_window_clipping_splits_a_connected_region(self):
        u = (((0, 0), (3, 0), (3, 3), (2, 3), (2, 1),
              (1, 1), (1, 3), (0, 3), (0, 0)),)
        r1, r2 = self._put_pair("p", box(10, 10, 11, 11), u)
        out = self.analysis.changes("p", r1, r2, (0, 2, 3, 3))
        self.assertEqual(out, {"gained": (F(1), F(1)), "lost": ()})

    def test_partial_collinear_overlap_accepted_across_revisions(self):
        r1, r2 = self._put_pair("p", box(0, 0, 2, 2), box(1, 0, 3, 2))
        out = self.analysis.changes("p", r1, r2, (-1, -1, 4, 3))
        self.assertEqual(out, {"gained": (F(2),), "lost": (F(2),)})

    def test_identical_revisions_and_reverse_orientation(self):
        r1, r2 = self._put_pair("p", DONUT, DONUT)
        self.assertEqual(self.analysis.changes("p", r1, r2, (3, -1, 9, 5)),
                         {"gained": (), "lost": ()})
        flipped = tuple(tuple(reversed(ring)) for ring in DONUT)
        r3, r4 = self._put_pair("q", DONUT, flipped)
        self.assertEqual(self.analysis.changes("q", r3, r4, (3, -1, 9, 5)),
                         {"gained": (), "lost": ()})

    def test_rational_triangle_clipped_by_window(self):
        r1, r2 = self._put_pair("p", box(10, 10, 11, 11), triangle())
        out = self.analysis.changes("p", r1, r2, (0, 0, 1, 3))
        self.assertEqual(out, {"gained": (F(5, 2),), "lost": ()})

    def test_fraction_coordinates_and_sorting(self):
        old = box(F(1, 3), F(1, 3), F(2, 3), F(2, 3))
        new = box(F(4, 3), F(1, 3), F(5, 3), F(2, 3))
        r1, r2 = self._put_pair("p", old, new)
        out = self.analysis.changes("p", r1, r2, (0, 0, 2, 1))
        self.assertTrue(all(type(v) is F for v in out["gained"] + out["lost"]))
        self.assertEqual(out["gained"], tuple(sorted(out["gained"])))
        self.assertEqual(out["lost"], tuple(sorted(out["lost"])))


class OracleAgreementTests(unittest.TestCase):
    """The vertical engine and horizontal reference must always agree."""

    def test_public_cases_match_reference_in_both_directions(self):
        for name, old, new, window, _, _ in CASES:
            with self.subTest(case=name):
                g, l = component_areas(old, new, window)
                rg, rl = reference_components(old, new, window)
                self.assertEqual((g, l), (rg, rl), name)
                g2, l2 = component_areas(new, old, window)
                rg2, rl2 = reference_components(new, old, window)
                self.assertEqual((g2, l2), (rg2, rl2), name)
                self.assertEqual((g2, l2), (l, g))

    def test_partial_window_grid_matches_reference(self):
        old = DONUT
        new = box(4, 0, 8, 4)
        for x0 in (3, 4, 5):
            for y0 in (-1, 0, 1):
                window = (F(x0), F(y0), F(x0 + 2), F(y0 + 3))
                with self.subTest(window=window):
                    self.assertEqual(
                        component_areas(old, new, window),
                        reference_components(old, new, window))

    def test_contact_only_never_connects(self):
        # Lobes touching at a single corner stay separate under both engines.
        new = box(0, 0, 1, 1) + box(1, 1, 2, 2)
        old = box(10, 10, 11, 11)
        window = (-1, -1, 3, 3)
        self.assertEqual(component_areas(old, new, window),
                         reference_components(old, new, window))

    def test_area_balance_identity(self):
        from vendor.ring1 import Region
        for name, old, new, window, gained, lost in CASES:
            with self.subTest(case=name):
                g, l = component_areas(old, new, window)
                delta = Region(new).area(window) - Region(old).area(window)
                self.assertEqual(sum(g, F(0)) - sum(l, F(0)), delta)


if __name__ == "__main__":
    unittest.main()
