import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))

from function import (
    SVG_TAG,
    _autocrop_transparent,
    add_board_image,
    add_pin_graphics,
    create_svg_root,
    detect_pin,
    detect_side_pin,
    read_image,
    render_pinout,
    scale_image_to_svg,
    svg_to_png,
)
from Pin import Pin


class TestFunctionModule(unittest.TestCase):

    def test_detect_side_pin_all_four_sides(self):
        svg_size = (100.0, 100.0)
        # Left edge
        self.assertEqual(detect_side_pin(5.0, 50.0, svg_size), 'left')
        # Right edge
        self.assertEqual(detect_side_pin(95.0, 50.0, svg_size), 'right')
        # Top edge
        self.assertEqual(detect_side_pin(50.0, 5.0, svg_size), 'top')
        # Bottom edge
        self.assertEqual(detect_side_pin(50.0, 95.0, svg_size), 'bottom')

    def test_detect_side_pin_aspect_ratios(self):
        # Landscape board: 100 x 40
        landscape = (100.0, 40.0)
        self.assertEqual(detect_side_pin(20.0, 20.0, landscape), 'left')
        self.assertEqual(detect_side_pin(80.0, 20.0, landscape), 'right')
        self.assertEqual(detect_side_pin(50.0, 2.0, landscape), 'top')
        self.assertEqual(detect_side_pin(50.0, 38.0, landscape), 'bottom')

        # Portrait board: 30 x 100
        portrait = (30.0, 100.0)
        self.assertEqual(detect_side_pin(15.0, 20.0, portrait), 'top')
        self.assertEqual(detect_side_pin(15.0, 80.0, portrait), 'bottom')
        self.assertEqual(detect_side_pin(2.0, 50.0, portrait), 'left')
        self.assertEqual(detect_side_pin(28.0, 50.0, portrait), 'right')

    def test_detect_pin_spatial_sorting(self):
        root = ET.Element('svg')
        # Add circle pads in arbitrary scrambled order
        # Left pins: (2, 40), (2, 10)
        # Right pins: (98, 30), (98, 10)
        # Top pin: (50, 2)
        # Bottom pin: (50, 98)
        ET.SubElement(root, 'circle', {'cx': '98', 'cy': '30', 'r': '0.85'})
        ET.SubElement(root, 'circle', {'cx': '2', 'cy': '40', 'r': '0.85'})
        ET.SubElement(root, 'circle', {'cx': '50', 'cy': '98', 'r': '0.85'})
        ET.SubElement(root, 'circle', {'cx': '2', 'cy': '10', 'r': '0.85'})
        ET.SubElement(root, 'circle', {'cx': '50', 'cy': '2', 'r': '0.85'})
        ET.SubElement(root, 'circle', {'cx': '98', 'cy': '10', 'r': '0.85'})

        pins = detect_pin(root.iter(), (100.0, 100.0), sort_pins=True)
        self.assertEqual(len(pins), 6)

        # Left pins sorted top-down
        self.assertEqual(pins[0].side, 'left')
        self.assertAlmostEqual(pins[0].cy, 10.0)
        self.assertEqual(pins[1].side, 'left')
        self.assertAlmostEqual(pins[1].cy, 40.0)

        # Top pin
        self.assertEqual(pins[2].side, 'top')
        self.assertAlmostEqual(pins[2].cx, 50.0)

        # Right pins sorted top-down
        self.assertEqual(pins[3].side, 'right')
        self.assertAlmostEqual(pins[3].cy, 10.0)
        self.assertEqual(pins[4].side, 'right')
        self.assertAlmostEqual(pins[4].cy, 30.0)

        # Bottom pin
        self.assertEqual(pins[5].side, 'bottom')
        self.assertAlmostEqual(pins[5].cy, 98.0)

        # Check numbers are 1..6
        self.assertEqual([p.number for p in pins], [1, 2, 3, 4, 5, 6])

    def test_add_pin_graphics_all_sides(self):
        root = create_svg_root(100, 100)

        for side, cx, cy in [('left', 10, 50), ('right', 90, 50), ('top', 50, 10), ('bottom', 50, 90)]:
            pin = Pin(cx=cx, cy=cy, r=0.85, number=1, side=side)
            pin.add_function("TEST_LABEL_1", "#E83131")
            pin.add_function("VERY_LONG_SECONDARY_FUNCTION_NAME", "#439ED6")
            add_pin_graphics(root, pin)

        # Group count should be 4
        groups = [el for el in root.iter() if el.tag.endswith('g') and 'id' in el.attrib and 'functions' not in el.attrib['id']]
        self.assertEqual(len(groups), 4)

    def test_autocrop_transparent(self):
        # Create an RGBA image with transparent margins
        img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        # Draw a solid opaque box in the center (20, 20) to (80, 80)
        for x in range(20, 80):
            for y in range(20, 80):
                img.putpixel((x, y), (255, 0, 0, 255))

        cropped = _autocrop_transparent(img)
        self.assertEqual(cropped.size, (60, 60))

    def test_scale_image_to_svg(self):
        sw, sh = scale_image_to_svg(200, 100, 50, 50)
        self.assertAlmostEqual(sw, 50.0)
        self.assertAlmostEqual(sh, 25.0)

    def test_render_pinout_end_to_end(self):
        # Create a sample test image
        tmp_img = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp_img.close()
        img = Image.new('RGBA', (200, 200), (34, 139, 34, 255))
        img.save(tmp_img.name, 'PNG')

        tmp_out = tempfile.NamedTemporaryFile(suffix='.svg', delete=False)
        tmp_out.close()

        try:
            pins = [
                Pin(cx=5.0, cy=10.0, r=0.85, number=1, side='left'),
                Pin(cx=5.0, cy=20.0, r=0.85, number=2, side='left'),
                Pin(cx=25.0, cy=10.0, r=0.85, number=3, side='right'),
                Pin(cx=15.0, cy=2.0, r=0.85, number=4, side='top'),
                Pin(cx=15.0, cy=28.0, r=0.85, number=5, side='bottom'),
            ]
            pins[0].add_function("VCC", "#E83131")
            pins[1].add_function("GND", "#363A44")
            pins[2].add_function("TX", "#9D89CE")
            pins[2].add_function("GPIO1", "#7AC943")
            pins[3].add_function("RESET", "#F6ADAD")
            pins[4].add_function("BOOT", "#EA8326")

            out_file = render_pinout(pins, tmp_img.name, (30.0, 30.0), tmp_out.name, export_png=True)
            self.assertTrue(os.path.isfile(out_file))
            self.assertGreater(os.path.getsize(out_file), 0)

            # Check that SVG contains valid XML
            tree = ET.parse(out_file)
            self.assertIsNotNone(tree.getroot())

        finally:
            for p in [tmp_img.name, tmp_out.name, os.path.splitext(tmp_out.name)[0] + '.png']:
                if os.path.isfile(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass


if __name__ == '__main__':
    unittest.main()
