import unittest
from fractions import Fraction as F
from geometry import normalize_rings
from samples import BUTTERFLY, DONUT, CROSSING, L_SHAPE
from vendor.ring1 import Region
from vendor.face2 import Face

class RingTests(unittest.TestCase):
    def test_butterfly_position_and_original_boundary(self):
        region = Region(BUTTERFLY)
        self.assertEqual(region.area(), 2)
        for window, area in (((0, 0, 2, 1), 1), ((0, 1, 2, 2), 1),
                             ((0, 0, 1, 1), F(1, 2)),
                             ((F(1, 2), F(1, 2), F(3, 2), F(3, 2)), F(1, 2))):
            self.assertEqual(region.area(window), area)
        self.assertFalse(region.contains((F(1, 4), 1)))
        self.assertTrue(region.contains((1, F(1, 4))))
        # A vertical line inside the lower lobe is not an original boundary.
        line = (1, F(1, 4), 1, F(1, 2))
        self.assertTrue(region.intersects(line))
        self.assertEqual(region.area(line), 0)
        self.assertFalse(region.boundary_touches(line))
        self.assertTrue(region.boundary_touches((1, 1, 1, 1)))
        self.assertFalse(region.intersects((F(1, 10), F(9, 10), F(1, 5), F(11, 10))))

    def test_rational_affine_family(self):
        # Hand-derived area of each lobe is sx*sy; both orientations agree.
        for sx, sy, ox, oy in ((F(1, 3), F(5, 7), -4, 2),
                                (F(7, 2), F(2, 9), 5, -3), (2, 3, 0, 0)):
            rings = tuple(tuple((ox + sx*x, oy + sy*y) for x, y in ring)
                          for ring in BUTTERFLY)
            for candidate in (rings, tuple(tuple(reversed(r)) for r in rings)):
                region = Region(candidate)
                self.assertEqual(region.area(), 2*sx*sy)
                self.assertEqual(region.area((ox, oy+sy, ox+2*sx, oy+2*sy)), sx*sy)

    def test_holes_crossing_rings_and_tangency(self):
        donut = Region(DONUT)
        self.assertEqual(donut.area(), 12)
        self.assertEqual(donut.area((5, 1, 7, 3)), 0)
        self.assertTrue(donut.intersects((5, 1, 7, 3)))
        self.assertFalse(donut.intersects((6, 2, 6, 2)))
        xor = Region(CROSSING)
        self.assertEqual(xor.area(), 14)
        self.assertFalse(xor.intersects((F(9, 4), F(5, 4), F(11, 4), F(11, 4))))
        self.assertTrue(xor.intersects((3, 1, 3, 1)))
        self.assertEqual(xor.area((2, 1, 3, 3)), 0)

    def test_input_rejection_and_sequence_preservation(self):
        for rings in ((), (((0, 0), (1, 0), (0, 1)),),
                      (((0, 0), (1, 0), (1, 0), (0, 0)),),
                      (((0, 0), (2, 0), (1, 0), (0, 1), (0, 0)),),
                      (((0.0, 0), (1, 0), (0, 1), (0, 0)),)):
            with self.subTest(rings=rings), self.assertRaises(ValueError):
                Region(rings)
        raw = ((("0", "0"), ("1/3", "0"), ("0", "0.5"), ("0", "0")),)
        self.assertEqual(normalize_rings(raw)[0][1], (F(1, 3), F(0)))
        with self.assertRaises(ValueError):
            Region(BUTTERFLY).area((2, 0, 1, 1))

class FaceTests(unittest.TestCase):
    def test_simple_validation_and_concave_clip(self):
        with self.assertRaises(ValueError):
            Face(BUTTERFLY[0])
        with self.assertRaises(ValueError):
            Face(((0, 0), (2, 0), (2, 2), (1, 0), (0, 2), (0, 0)))
        for vertices in (L_SHAPE[0], tuple(reversed(L_SHAPE[0]))):
            face = Face(vertices)
            self.assertEqual(face.area(), 5)
            self.assertEqual(face.area((10, 0, 12, 2)), 3)
            self.assertEqual(face.area((11, 1, 12, 2)), 0)
            self.assertTrue(face.intersects((11, 1, 12, 2)))
            self.assertFalse(face.intersects((12, 2, 13, 3)))
        # The clip has two disconnected arms; bridge edges contribute no area.
        u = Face(((0, 0), (3, 0), (3, 3), (2, 3), (2, 1),
                  (1, 1), (1, 3), (0, 3), (0, 0)))
        self.assertEqual(u.area((0, 2, 3, 3)), 2)
        self.assertFalse(u.intersects((F(5, 4), 2, F(7, 4), 3)))

    def test_independent_sdk_area_paths(self):
        # SDK1 integrates lengths; SDK2 clips vertices then uses signed area.
        faces = (L_SHAPE[0], ((0, 0), (4, 0), (1, 3), (0, 0)),
                 ((0, 0), (3, 0), (3, 3), (2, 3), (2, 1),
                  (1, 1), (1, 3), (0, 3), (0, 0)))
        for vertices in faces:
            old, new = Region((vertices,)), Face(vertices)
            for x in range(-1, 14):
                for y in range(-1, 4):
                    window = (F(x, 2), F(y, 2), F(x, 2)+F(4, 3), F(y, 2)+F(5, 4))
                    with self.subTest(vertices=vertices, window=window):
                        self.assertEqual(new.area(window), old.area(window))
                        self.assertEqual(new.intersects(window), old.intersects(window))
