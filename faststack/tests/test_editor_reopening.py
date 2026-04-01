import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure we can import faststack
sys.path.append(str(Path(__file__).parents[2]))

from faststack.app import AppController

class TestEditorReopening(unittest.TestCase):
    def setUp(self):
        # 1. Heavily patch all external-touching classes
        self.patchers = [
            patch("faststack.app.Watcher"),
            patch("faststack.app.SidecarManager"),
            patch("faststack.app.Prefetcher"),
            patch("faststack.app.ByteLRUCache"),
            patch("faststack.app.ThumbnailProvider"),
            patch("faststack.app.config"),
            patch("faststack.app.setup_logging"),
            patch("faststack.app.UIState"),
            patch("faststack.app.QTimer"), # <-- Fix QObject/Timer issues in headless tests
            patch("faststack.app.create_daemon_threadpool_executor"),
            patch("concurrent.futures.ThreadPoolExecutor"),
        ]
        for p in self.patchers:
            p.start()

        # 2. Instantiate controller
        self.controller = AppController(Path("."), MagicMock())
        
        # 3. Setup mocks for editor session logic
        self.controller.image_editor = MagicMock()
        self.controller.image_editor.current_filepath = Path("test.jpg")
        self.controller.image_editor.current_mtime = 123.4
        self.controller.image_editor.session_id = "test-session"
        
        # Setup files
        mock_file = MagicMock()
        mock_file.path = Path("test.jpg")
        self.controller.image_files = [mock_file]
        self.controller.current_index = 0

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    def test_save_failure_retains_editor_state(self):
        # Simulate background worker callback firing with a failure
        save_ctx = {
            "image_key": str(Path("test.jpg").resolve()),
            "session_id": "test-session",
            "editor_was_open": True
        }
        result = {"success": False, "error": "Disk full"}
        
        # Post-save cleanup path
        self.controller._on_save_finished(result, save_ctx)
        
        # VERIFY: Clear must NOT be called on failure
        self.controller.image_editor.clear.assert_not_called()

    def test_reopen_hits_reuse_path_on_matching_file(self):
        target = Path("test.jpg")
        self.controller.image_editor.current_filepath = target
        self.controller.image_editor.current_mtime = 123.4
        
        with patch("pathlib.Path.resolve", return_value=target.absolute()):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_mtime = 123.4
                
                # REOPEN
                res = self.controller.load_image_for_editing()
                
                self.assertTrue(res)
                # VERIFY: reuse signals
                self.controller.ui_state.editorImageChanged.emit.assert_called_once()
                # VERIFY: no reload performed
                self.controller.image_editor.load_image.assert_not_called()

    def test_load_failure_closes_dialog(self):
        # Case 1: load_image fails
        self.controller.ui_state.isEditorOpen = True
        self.controller.image_editor.current_filepath = None # Ensure no reuse
        self.controller.image_editor.load_image.return_value = False
        
        res = self.controller.load_image_for_editing()
        self.assertFalse(res)
        self.assertFalse(self.controller.ui_state.isEditorOpen, "Dialog should close on failure")
        
        # Case 2: exception throws
        self.controller.ui_state.isEditorOpen = True
        self.controller.image_editor.load_image.side_effect = RuntimeError("IO error")
        res = self.controller.load_image_for_editing()
        self.assertFalse(res)
        self.assertFalse(self.controller.ui_state.isEditorOpen, "Dialog should close on error")

if __name__ == "__main__":
    unittest.main()
