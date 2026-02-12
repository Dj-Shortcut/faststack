import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from faststack.app import AppController
from faststack.models import ImageFile


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for tests that might touch UI elements."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_controller(tmp_path, qapp):
    """Creates an AppController with mocked dependencies."""
    engine = Mock()

    with (
        patch("faststack.app.Watcher"),
        patch("faststack.app.SidecarManager"),
        patch("faststack.app.ImageEditor"),
        patch("faststack.app.ByteLRUCache"),
        patch("faststack.app.Prefetcher"),
        patch("faststack.app.ThumbnailCache"),
        patch("faststack.app.ThumbnailPrefetcher"),
        patch("faststack.app.ThumbnailModel"),
        patch("faststack.app.ThumbnailProvider"),
        patch("faststack.app.UIState"),
        patch("faststack.app.QCoreApplication"),
        patch("faststack.app.Keybinder"),
    ):
        controller = AppController(tmp_path, engine)

        # Mock the executor to prevent background jobs from running during tests
        from concurrent.futures import Future
        controller._delete_executor = Mock()
        controller._delete_executor.submit.side_effect = lambda *a, **kw: Future()

        controller.dataChanged = Mock()
        controller.dataChanged.emit = Mock()
        controller.sync_ui_state = Mock()
        controller._do_prefetch = Mock()
        controller.update_status_message = Mock()
        controller._thumbnail_model = Mock()
        controller._thumbnail_model.rowCount.return_value = 0

        return controller


def test_delete_current_image_optimistic_ui(mock_controller):
    """Test that delete_current_image performs optimistic UI removal immediately."""
    img1 = ImageFile(Path("test1.jpg"))
    img2 = ImageFile(Path("test2.jpg"))
    mock_controller.image_files = [img1, img2]
    mock_controller.current_index = 0
    mock_controller.undo_history = []
    mock_controller.refresh_image_list = Mock()
    mock_controller.image_cache = Mock()
    mock_controller.prefetcher = Mock()

    mock_controller.delete_current_image()

    # Optimistic UI: image removed immediately
    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0] == img2

    # Verify cache/prefetch cleanup happened immediately
    mock_controller.image_cache.clear.assert_called_once()
    mock_controller.prefetcher.cancel_all.assert_called_once()
    mock_controller.sync_ui_state.assert_called_once()

    # Verify undo history has pending_delete entry
    assert len(mock_controller.undo_history) == 1
    assert mock_controller.undo_history[0][0] == "pending_delete"


def test_delete_async_completion(mock_controller, tmp_path):
    """Test that async deletion completes and updates undo history."""
    img_path = tmp_path / "test1.jpg"
    img_path.write_text("content")
    img1 = ImageFile(img_path)
    img2 = ImageFile(Path("test2.jpg"))
    mock_controller.image_files = [img1, img2]
    mock_controller.current_index = 0
    mock_controller.undo_history = []
    mock_controller.refresh_image_list = Mock()
    mock_controller.image_cache = Mock()
    mock_controller.prefetcher = Mock()

    mock_controller.delete_current_image()

    # Get job_id and manually call completion handler
    job_id = list(mock_controller._pending_delete_jobs.keys())[0]

    # Use resolve() for deterministic path matching in handler
    img_path_resolved = img_path.resolve()
    recycle_bin = (tmp_path / "image recycle bin").resolve()
    recycle_bin.mkdir(exist_ok=True)
    recycled = (recycle_bin / img_path.name).resolve()

    # Structured dict result
    result = {
        "job_id": job_id,
        "successes": [{
            "jpg": img_path_resolved,
            "recycled_jpg": recycled,
            "raw": None,
            "recycled_raw": None
        }],
        "failures": [],
        "cancelled": False,
    }
    mock_controller._on_delete_finished(result)

    # pending_delete replaced by delete entry
    delete_entries = [e for e in mock_controller.undo_history if e[0] == "delete"]
    assert len(delete_entries) == 1
    pending_entries = [e for e in mock_controller.undo_history if e[0] == "pending_delete"]
    assert len(pending_entries) == 0

    mock_controller.update_status_message.assert_called_with(
        "Image moved to recycle bin"
    )


def test_delete_current_image_cancel(mock_controller):
    """Test undo while pending preserves image."""
    img1 = ImageFile(Path("test1.jpg"))
    mock_controller.image_files = [img1]
    mock_controller.current_index = 0
    mock_controller.image_cache = Mock()
    mock_controller.prefetcher = Mock()

    mock_controller.delete_current_image()
    assert len(mock_controller.image_files) == 0

    # Undo while still pending
    mock_controller.undo_delete()

    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0] == img1


def test_recycle_failure_restores_image_automatically(mock_controller):
    """Test that recycle bin failure restores the image to UI (Best-effort simplified semantics)."""
    img1 = ImageFile(Path("test1.jpg"))
    mock_controller.image_files = [img1]
    mock_controller.current_index = 0
    mock_controller.image_cache = Mock()
    mock_controller.prefetcher = Mock()

    summary = mock_controller._delete_indices([0], "test")
    job_id = summary["job_id"]

    # Simulate worker: recycle failed
    result = {
        "job_id": job_id,
        "successes": [],
        "failures": [{
            "jpg": img1.path.resolve(),
            "raw": None,
            "code": "recycle_failed"
        }],
        "cancelled": False,
    }

    # No prompt expected now
    with patch("faststack.app.confirm_permanent_delete") as mock_confirm:
        mock_controller._on_delete_finished(result)
        mock_confirm.assert_not_called()

    # Image should be restored/rolled back to the UI
    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0] == img1
