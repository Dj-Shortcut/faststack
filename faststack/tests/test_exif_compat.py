
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from PIL import Image
import numpy as np
import io

# Adjust path to import faststack
import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))

from faststack.imaging.editor import ImageEditor

class TestExifCompat(unittest.TestCase):
    def setUp(self):
        self.editor = ImageEditor()
        # Create a dummy image for testing
        self.editor.original_image = Image.new('RGB', (10, 10))
        self.editor._source_exif_bytes = b"dummy exif bytes"

    def test_missing_image_exif_attribute(self):
        """Test fallback when PIL.Image.Exif is missing."""
        # Patching PIL.Image.Exif to raise AttributeError on access simulates it being missing
        with patch('PIL.Image.Exif', side_effect=AttributeError):
            # Also mock getexif to verify it's the fallback
            self.editor.original_image.getexif = MagicMock(return_value=None)
            self.editor._get_sanitized_exif_bytes()
            self.editor.original_image.getexif.assert_called_once()

    def test_missing_load_method(self):
        """Test fallback when Exif object has no load() method."""
        mock_exif_instance = MagicMock()
        del mock_exif_instance.load
        
        with patch('PIL.Image.Exif', return_value=mock_exif_instance):
            # Should fall back to original_image.getexif()
            self.editor.original_image.getexif = MagicMock(return_value=None)
            self.editor._get_sanitized_exif_bytes()
            self.editor.original_image.getexif.assert_called_once()

    def test_missing_tobytes_method(self):
        """Test graceful failure when Exif object has no tobytes() method."""
        mock_exif_instance = MagicMock()
        if hasattr(mock_exif_instance, 'tobytes'):
            del mock_exif_instance.tobytes
        
        # Mocking getexif to return this broken instance
        self.editor.original_image.getexif = MagicMock(return_value=mock_exif_instance)
        self.editor._source_exif_bytes = None
        
        res = self.editor._get_sanitized_exif_bytes()
        self.assertIsNone(res, "Should return None if tobytes() is missing")

    def test_missing_exiftags_base(self):
        """Test fallback when ExifTags.Base is missing (older Pillow)."""
        # Patch PIL.ExifTags to be a mock that does NOT have 'Base'
        # This will cause ExifTags.Base to raise AttributeError
        with patch('PIL.ExifTags', spec=[]):
            # Use a mock that doesn't restrict attributes, but has tobytes
            mock_exif = MagicMock()
            mock_exif.tobytes = MagicMock(return_value=b"serialized exif")
            self.editor.original_image.getexif = MagicMock(return_value=mock_exif)
            self.editor._source_exif_bytes = None
            
            res = self.editor._get_sanitized_exif_bytes()
            # Check if it tried to set 0x0112 (the fallback)
            mock_exif.__setitem__.assert_called_with(0x0112, 1)
            self.assertEqual(res, b"serialized exif")

if __name__ == '__main__':
    unittest.main()
