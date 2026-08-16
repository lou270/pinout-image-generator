import math
import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))

import svg


class TestSvgModule(unittest.TestCase):

    def test_distance(self):
        self.assertAlmostEqual(svg.distance((0, 0), (3, 4)), 5.0)
        self.assertAlmostEqual(svg.distance((1, 1), (1, 1)), 0.0)

    def test_normalize(self):
        nx, ny = svg.normalize((3, 4))
        self.assertAlmostEqual(nx, 0.6)
        self.assertAlmostEqual(ny, 0.8)
        self.assertEqual(svg.normalize((0, 0)), (0, 0))

    def test_move_point_along_vector(self):
        pt = svg.move_point_along_vector((10, 10), (1, 0), 5)
        self.assertEqual(pt, (15, 10))

    def test_scale_point(self):
        self.assertEqual(svg.scale_point((2, 3), 2, 4), (4, 12))

    def test_parse_and_extract_svg_path(self):
        d = "M 0 0 L 10 0 L 10 10 Z"
        pts = svg.extract_points_from_path(d)
        self.assertGreaterEqual(len(pts), 4)
        self.assertEqual(pts[0], (0.0, 0.0))
        self.assertEqual(pts[1], (10.0, 0.0))

    def test_round_path_corners(self):
        d = "M 0,0 L 10,0 L 10,10 L 0,10 Z"
        rounded = svg.round_path_corners(d, 0.5)
        self.assertTrue(rounded.startswith("M"))
        self.assertTrue("Q" in rounded)
        self.assertTrue(rounded.endswith("Z"))

    def test_get_min_max_and_size(self):
        root = ET.Element('svg')
        circle = ET.SubElement(root, 'circle', {'cx': '20', 'cy': '30', 'r': '5'})
        min_x, max_x, min_y, max_y = svg.get_min_max_pos(circle)
        self.assertAlmostEqual(min_x, 15.0)
        self.assertAlmostEqual(max_x, 25.0)
        self.assertAlmostEqual(min_y, 25.0)
        self.assertAlmostEqual(max_y, 35.0)
        w, h = svg.get_size(min_x, max_x, min_y, max_y)
        self.assertAlmostEqual(w, 10.0)
        self.assertAlmostEqual(h, 10.0)

    def test_shift_element(self):
        circle = ET.Element('circle', {'cx': '10', 'cy': '20', 'r': '2'})
        svg.shift_element(circle, 5, -5)
        self.assertAlmostEqual(float(circle.attrib['cx']), 15.0)
        self.assertAlmostEqual(float(circle.attrib['cy']), 15.0)

        rect = ET.Element('image', {'x': '10', 'y': '20', 'width': '5', 'height': '5'})
        svg.shift_element(rect, 2, 3)
        self.assertAlmostEqual(float(rect.attrib['x']), 12.0)
        self.assertAlmostEqual(float(rect.attrib['y']), 23.0)

    def test_update_bounding_box(self):
        root = ET.Element('{http://www.w3.org/2000/svg}svg')
        ET.SubElement(root, '{http://www.w3.org/2000/svg}circle', {'cx': '10', 'cy': '20', 'r': '5'})
        ET.SubElement(root, '{http://www.w3.org/2000/svg}circle', {'cx': '40', 'cy': '50', 'r': '5'})

        w, h = svg.update_bounding_box(root, margin=2)
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        self.assertTrue('viewBox' in root.attrib)
        self.assertTrue(root.attrib['viewBox'].startswith('0 0'))


if __name__ == '__main__':
    unittest.main()
