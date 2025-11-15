import unittest
import sys
import os

# Add the parent directory to sys.path so we can import the add-on modules
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)


# Calculation functions extracted from the add-on logic
# These mirror the calculations in properties.py update functions
def calculate_throw_ratio(distance, image_width):
    """
    Calculate throw ratio from distance and image width.
    Formula: TR = D / W
    """
    if image_width <= 0:
        return float('inf')
    return distance / image_width


def calculate_image_width(distance, throw_ratio):
    """
    Calculate image width from distance and throw ratio.
    Formula: W = D / TR
    """
    if throw_ratio <= 0:
        return float('inf')
    return distance / throw_ratio


def calculate_throw_distance(image_width, throw_ratio):
    """
    Calculate throw distance from image width and throw ratio.
    Formula: D = W * TR
    """
    return image_width * throw_ratio


def calculate_image_height(image_width, aspect_ratio_w, aspect_ratio_h):
    """
    Calculate image height from width and aspect ratio.
    Formula: H = W * (AR_h / AR_w)
    """
    if aspect_ratio_w <= 0:
        return 0
    return image_width * (aspect_ratio_h / aspect_ratio_w)


class TestCalculations(unittest.TestCase):
    """Test cases for the core projection calculations."""

    def test_throw_ratio_calculation(self):
        """Test the throw ratio calculation: TR = D / W"""
        # Test with normal values
        self.assertAlmostEqual(calculate_throw_ratio(6.0, 3.0), 2.0)
        self.assertAlmostEqual(calculate_throw_ratio(4.0, 2.0), 2.0)
        self.assertAlmostEqual(calculate_throw_ratio(10.0, 5.0), 2.0)

        # Test with different ratios
        self.assertAlmostEqual(calculate_throw_ratio(3.0, 2.0), 1.5)
        self.assertAlmostEqual(calculate_throw_ratio(8.0, 4.0), 2.0)

        # Edge case: zero width (should return inf)
        self.assertEqual(calculate_throw_ratio(5.0, 0.0), float('inf'))

        # Edge case: negative width (should return inf)
        self.assertEqual(calculate_throw_ratio(5.0, -1.0), float('inf'))

    def test_image_width_calculation(self):
        """Test the image width calculation: W = D / TR"""
        # Test with normal values
        self.assertAlmostEqual(calculate_image_width(6.0, 2.0), 3.0)
        self.assertAlmostEqual(calculate_image_width(4.0, 2.0), 2.0)
        self.assertAlmostEqual(calculate_image_width(10.0, 2.5), 4.0)

        # Test with different ratios
        self.assertAlmostEqual(calculate_image_width(3.0, 1.5), 2.0)
        self.assertAlmostEqual(calculate_image_width(8.0, 2.0), 4.0)

        # Edge case: zero throw ratio (should return inf)
        self.assertEqual(calculate_image_width(5.0, 0.0), float('inf'))

        # Edge case: negative throw ratio (should return inf)
        self.assertEqual(calculate_image_width(5.0, -1.0), float('inf'))

    def test_throw_distance_calculation(self):
        """Test the throw distance calculation: D = W * TR"""
        # Test with normal values
        self.assertAlmostEqual(calculate_throw_distance(3.0, 2.0), 6.0)
        self.assertAlmostEqual(calculate_throw_distance(2.0, 2.0), 4.0)
        self.assertAlmostEqual(calculate_throw_distance(4.0, 2.5), 10.0)

        # Test with different ratios
        self.assertAlmostEqual(calculate_throw_distance(2.0, 1.5), 3.0)
        self.assertAlmostEqual(calculate_throw_distance(4.0, 2.0), 8.0)

        # Edge case: zero values
        self.assertAlmostEqual(calculate_throw_distance(0.0, 2.0), 0.0)
        self.assertAlmostEqual(calculate_throw_distance(3.0, 0.0), 0.0)

    def test_image_height_calculation(self):
        """Test the image height calculation: H = W * (AR_h / AR_w)"""
        # Test with 16:9 aspect ratio
        self.assertAlmostEqual(calculate_image_height(16.0, 16, 9), 9.0)
        self.assertAlmostEqual(calculate_image_height(3.2, 16, 9), 1.8)

        # Test with 4:3 aspect ratio
        self.assertAlmostEqual(calculate_image_height(4.0, 4, 3), 3.0)
        self.assertAlmostEqual(calculate_image_height(8.0, 4, 3), 6.0)

        # Test with 21:9 aspect ratio (ultrawide)
        self.assertAlmostEqual(calculate_image_height(21.0, 21, 9), 9.0)

        # Edge case: zero aspect width
        self.assertEqual(calculate_image_height(10.0, 0, 9), 0)

        # Edge case: negative aspect width
        self.assertEqual(calculate_image_height(10.0, -16, 9), 0)

    def test_bidirectional_consistency(self):
        """Test that forward and backward calculations are consistent"""
        # Start with known values
        distance = 6.0
        width = 3.0

        # Calculate throw ratio
        tr = calculate_throw_ratio(distance, width)
        self.assertAlmostEqual(tr, 2.0)

        # Calculate width back from distance and throw ratio
        calculated_width = calculate_image_width(distance, tr)
        self.assertAlmostEqual(calculated_width, width)

        # Calculate distance from width and throw ratio
        calculated_distance = calculate_throw_distance(width, tr)
        self.assertAlmostEqual(calculated_distance, distance)

    def test_realistic_projector_scenarios(self):
        """Test with realistic projector setup values"""
        # Short throw projector (TR = 0.5)
        distance = 2.0  # 2 meters from wall
        tr = 0.5
        width = calculate_image_width(distance, tr)
        self.assertAlmostEqual(width, 4.0)  # 4 meter wide image

        # Standard throw projector (TR = 1.5)
        distance = 6.0  # 6 meters from wall
        tr = 1.5
        width = calculate_image_width(distance, tr)
        self.assertAlmostEqual(width, 4.0)  # 4 meter wide image

        # Long throw projector (TR = 2.5)
        distance = 10.0  # 10 meters from wall
        tr = 2.5
        width = calculate_image_width(distance, tr)
        self.assertAlmostEqual(width, 4.0)  # 4 meter wide image

        # Calculate image height for 16:9 aspect ratio
        height = calculate_image_height(4.0, 16, 9)
        self.assertAlmostEqual(height, 2.25)  # 4m * (9/16) = 2.25m


if __name__ == '__main__':
    unittest.main() 