import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from faststack.app import AppController

@pytest.fixture
def controller(tmp_path):
    with (
        patch('faststack.app.Watcher'),
        patch('faststack.app.SidecarManager'),
        patch('faststack.app.setup_logging'),
        patch('faststack.app.QQmlApplicationEngine'),
        patch('faststack.app.ThumbnailModel'),
    ):
        ctrl = AppController(tmp_path, Mock())
        ctrl._thumbnail_model = Mock()
        ctrl._path_resolver = Mock()
        return ctrl

def test_do_delete_refresh_skips_on_sync(controller):
    """Verify that skip logic works when counts are in sync."""
    controller.image_files = [Mock(), Mock()] # 2 images
    controller._thumbnail_model.rowCount.return_value = 3 # 2 images + 1 folder
    controller._thumbnail_model.folder_count = 1
    
    with patch('faststack.app._debug_mode', True):
        controller._do_delete_refresh()
        
    # Should NOT have called refresh_from_controller
    assert controller._thumbnail_model.refresh_from_controller.call_count == 0
    # Should have updated resolver
    assert controller._path_resolver.update_from_model.called

def test_do_delete_refresh_rebuilds_on_drift(controller):
    """Verify that skip logic fallback works when counts drift."""
    controller.image_files = [Mock(), Mock()] # 2 images
    controller._thumbnail_model.rowCount.return_value = 4 # DRIFT: expected 3
    controller._thumbnail_model.folder_count = 1
    
    with patch('faststack.app._debug_mode', True):
        controller._do_delete_refresh()
        
    # Should HAVE called refresh_from_controller
    assert controller._thumbnail_model.refresh_from_controller.called
    # Should have updated resolver
    assert controller._path_resolver.update_from_model.called
