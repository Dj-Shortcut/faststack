
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from pathlib import Path
import sys

# Ensure faststack is in path
from faststack.imaging.editor import ImageEditor
from PIL import Image

class TestDebugError(unittest.TestCase):
    def test_debug_save_image(self):
        editor = ImageEditor()
        editor.float_image = np.zeros((10, 10, 3), dtype=np.float32)
        editor.current_filepath = Path("fake_path.jpg")

        # Patch create_backup_file to succeed
        with patch("faststack.imaging.editor.create_backup_file", return_value=Path("backup.jpg")):
            # Patch Image.fromarray to return a mock that fails to save
            mock_img = MagicMock()
            mock_img.save.side_effect = PermissionError("Mocked save error")
            
            print(f"DEBUG: Real Image.fromarray before patch: {Image.fromarray}")

            with patch("PIL.Image.fromarray", return_value=mock_img) as mock_fromarray:
                print(f"DEBUG: Image.fromarray is patched: {Image.fromarray}")
                print(f"DEBUG: mock_fromarray: {mock_fromarray}")
                
                # Verify that calling Image.fromarray returns our mock
                img = Image.fromarray(np.zeros((10,10,3), dtype=np.uint8))
                print(f"DEBUG: Returned img: {img}")
                print(f"DEBUG: img.save side effect: {img.save.side_effect}")
                
                try:
                    editor.save_image()
                    print("FAIL: save_image did NOT raise RuntimeError")
                except RuntimeError as e:
                    print(f"PASS: Caught RuntimeError: {e}")
                except Exception as e:
                    print(f"FAIL: Caught unexpected exception: {type(e)} {e}")

if __name__ == "__main__":
    unittest.main()
