import unittest
import sys
from pathlib import Path
from PIL import Image, ExifTags
from faststack.imaging.editor import ImageEditor, sanitize_exif_orientation


class TestDebugExif(unittest.TestCase):
    def test_debug_exif(self):
        # Create source image with Orientation 6
        img = Image.new("RGB", (100, 50), color="red")
        exif = img.getexif()
        exif[ExifTags.Base.Orientation] = 6
        exif_bytes = exif.tobytes()

        print(f"DEBUG: Source EXIF bytes len: {len(exif_bytes)}")

        # Test sanitize_exif_orientation directly
        sanitized = sanitize_exif_orientation(exif_bytes)
        print(f"DEBUG: Sanitized bytes: {sanitized is not None}")

        if sanitized:
            chk = Image.Exif()
            chk.load(sanitized)
            print(f"DEBUG: Sanitized Orientation: {chk.get(ExifTags.Base.Orientation)}")

        # Helper to simulate editor flow
        editor = ImageEditor()
        editor.float_image = ImageEditor()._initial_edits()  # Dummy
        # ... actually need real flow


if __name__ == "__main__":
    unittest.main()
