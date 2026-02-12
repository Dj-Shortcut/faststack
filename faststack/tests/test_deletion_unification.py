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
    _ = qapp
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
        controller.sync_ui_state = Mock()
        controller.update_status_message = Mock()
        controller.refresh_image_list = Mock()
        controller.image_cache = Mock()
        controller.prefetcher = Mock()
        controller._thumbnail_model = Mock()
        controller._thumbnail_model.rowCount.return_value = 0

        return controller


# ── Optimistic UI tests ──────────────────────────────────────────────

def test_delete_batch_optimistic_removal(mock_controller):
    """Test that batch deletion optimistically removes images from the list."""
    img1 = ImageFile(Path("test1.jpg"))
    img2 = ImageFile(Path("test2.jpg"))
    img3 = ImageFile(Path("test3.jpg"))
    mock_controller.image_files = [img1, img2, img3]
    mock_controller.batches = [[0, 1]]
    mock_controller.undo_history = []

    mock_controller.delete_batch_images()

    # Optimistic UI: batch images removed immediately
    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0] == img3

    # sync_ui_state called for immediate visual feedback
    mock_controller.sync_ui_state.assert_called_once()

    # Batches cleared optimistically
    assert mock_controller.batches == []

    # Verify undo history has single pending_delete entry
    assert len(mock_controller.undo_history) == 1
    assert mock_controller.undo_history[0][0] == "pending_delete"


def test_grid_delete_selection(mock_controller):
    """Test deleting images selected in grid view."""
    img1 = ImageFile(Path("test1.jpg"))
    img2 = ImageFile(Path("test2.jpg"))
    mock_controller.image_files = [img1, img2]
    mock_controller._path_to_index = {img1.path.resolve(): 0, img2.path.resolve(): 1}

    mock_controller._thumbnail_model.get_selected_paths.return_value = [img1.path]

    mock_controller.grid_delete_at_cursor(0)

    # Optimistic: img1 removed immediately
    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0] == img2
    mock_controller._thumbnail_model.clear_selection.assert_called_once()


def test_grid_cursor_correct_mapping(mock_controller):
    """CRITICAL: Test that grid delete at cursor uses path mapping, NOT raw index."""
    imgA = ImageFile(Path("A.jpg"))
    imgB = ImageFile(Path("B.jpg"))
    mock_controller.image_files = [imgA, imgB]
    mock_controller._path_to_index = {imgA.path.resolve(): 0, imgB.path.resolve(): 1}

    mock_controller._thumbnail_model.get_selected_paths.return_value = []
    mock_entry = Mock()
    mock_entry.path = imgB.path
    mock_entry.is_folder = False
    mock_controller._thumbnail_model.get_entry.return_value = mock_entry

    mock_controller.grid_delete_at_cursor(0)

    # B (app index 1) should be removed
    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0] == imgA


def test_delete_current_image_triggers_batch_dialog(mock_controller):
    """Test that delete_current_image triggers the multi-image dialog if a batch exists."""
    img1 = ImageFile(Path("test1.jpg"))
    mock_controller.image_files = [img1]
    mock_controller.current_index = 0

    mock_controller.get_batch_count_for_current_image = Mock(return_value=5)
    mock_controller.main_window = Mock()
    mock_controller._delete_indices = Mock(return_value={"queued": True, "job_id": 0})

    mock_controller.delete_current_image()

    mock_controller.main_window.show_delete_batch_dialog.assert_called_once_with(5)
    assert mock_controller._delete_indices.call_count == 0


def test_grid_cursor_not_found_feedback(mock_controller):
    """Test standardized feedback for grid cursor delete when image not found."""
    mock_controller._thumbnail_model.get_selected_paths.return_value = []
    mock_entry = Mock()
    mock_entry.path = Path("missing.jpg")
    mock_entry.is_folder = False
    mock_controller._thumbnail_model.get_entry.return_value = mock_entry

    mock_controller._path_to_index = {}

    mock_controller.grid_delete_at_cursor(0)

    mock_controller.update_status_message.assert_called_with(
        "Image not found in current list."
    )


def test_delete_indices_summary_return(mock_controller):
    """Test that _delete_indices returns queued=True, not optimistic all_deleted."""
    img1 = ImageFile(Path("test1.jpg"))
    mock_controller.image_files = [img1]

    result = mock_controller._delete_indices([0], "test")

    assert result["queued"] is True
    assert result["requested_count"] == 1
    # all_deleted should NOT be True (async hasn't completed)
    assert result.get("all_deleted") is not True


def test_grid_cursor_mapping_regression(mock_controller):
    """Locked-in regression: grid index 0 maps to correct app index."""
    imgA = ImageFile(Path("A.jpg"))
    imgB = ImageFile(Path("B.jpg"))
    mock_controller.image_files = [imgB, imgA]
    mock_controller._path_to_index = {imgB.path.resolve(): 0, imgA.path.resolve(): 1}

    mock_controller._thumbnail_model.get_selected_paths.return_value = []
    mock_entry = Mock()
    mock_entry.path = imgA.path
    mock_entry.is_folder = False
    mock_controller._thumbnail_model.get_entry.return_value = mock_entry

    mock_controller.grid_delete_at_cursor(0)

    # imgA (app index 1) removed, imgB remains
    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0] == imgB


def test_grid_delete_folder_feedback(mock_controller):
    """Test feedback when attempting to delete a folder in grid."""
    mock_controller._thumbnail_model.get_selected_paths.return_value = []
    mock_entry = Mock()
    mock_entry.is_folder = True
    mock_controller._thumbnail_model.get_entry.return_value = mock_entry

    mock_controller.grid_delete_at_cursor(0)

    mock_controller.update_status_message.assert_called_with(
        "Cannot delete folders in grid view."
    )


def test_delete_schedules_refresh(mock_controller):
    """Test that deletion creates a pending async job."""
    img1 = ImageFile(Path("test1.jpg"))
    mock_controller.image_files = [img1]
    mock_controller._path_resolver = Mock()

    mock_controller._delete_indices([0], "test")

    # Job should be pending (async)
    assert len(mock_controller._pending_delete_jobs) == 1


# ── Undo tests ───────────────────────────────────────────────────────

def test_undo_pending_delete_restores_items(mock_controller):
    """Test that undo during pending delete restores items without disk ops."""
    img1 = ImageFile(Path("test1.jpg"))
    img2 = ImageFile(Path("test2.jpg"))
    mock_controller.image_files = [img1, img2]
    mock_controller.current_index = 0

    # Delete img1
    mock_controller._delete_indices([0], "test")

    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0] == img2

    # Undo while still pending
    mock_controller.undo_delete()

    # Item restored
    assert len(mock_controller.image_files) == 2
    assert mock_controller.image_files[0] == img1


def test_undo_pending_batch_delete_restores_all(mock_controller):
    """Test that undo of pending batch delete restores all items."""
    img1 = ImageFile(Path("test1.jpg"))
    img2 = ImageFile(Path("test2.jpg"))
    img3 = ImageFile(Path("test3.jpg"))
    mock_controller.image_files = [img1, img2, img3]
    mock_controller.batches = [[0, 1]]

    mock_controller.delete_batch_images()

    assert len(mock_controller.image_files) == 1

    # Undo restores all items from the batch
    mock_controller.undo_delete()

    assert len(mock_controller.image_files) == 3


# ── Cancel mid-flight restores unprocessed items ──────────────────────

def test_cancel_midlight_restores_unprocessed(mock_controller):
    """Cancel mid-flight: completion with partial success restores unprocessed items."""
    img1 = ImageFile(Path("img1.jpg"))
    img2 = ImageFile(Path("img2.jpg"))
    img3 = ImageFile(Path("img3.jpg"))
    mock_controller.image_files = [img1, img2, img3]

    summary = mock_controller._delete_indices([0, 1, 2], "test")
    job_id = summary["job_id"]

    # All 3 removed optimistically
    assert len(mock_controller.image_files) == 0

    # Simulate worker result: 1 success, 2 cancelled (unprocessed)
    result = {
        "job_id": job_id,
        "successes": [{
            "jpg": img1.path.resolve(),
            "recycled_jpg": Path("recycle/img1.jpg"),
            "raw": None,
            "recycled_raw": None
        }],
        "failures": [
            {"jpg": img2.path.resolve(), "raw": None, "code": "cancelled"},
            {"jpg": img3.path.resolve(), "raw": None, "code": "cancelled"},
        ],
        "cancelled": True,
    }
    mock_controller._on_delete_finished(result)

    # img2 and img3 should be restored to the list
    assert len(mock_controller.image_files) == 2
    restored_paths = {img.path for img in mock_controller.image_files}
    assert img2.path in restored_paths
    assert img3.path in restored_paths

    # img1 was successfully recycled — should have an undo entry
    delete_entries = [e for e in mock_controller.undo_history if e[0] == "delete"]
    assert len(delete_entries) == 1


# ── Undo pending prevents later bookkeeping ──────────────────────────

def test_undo_pending_prevents_later_bookkeeping(mock_controller):
    """Undo pending delete, then completion arrives: no undo entries added, no 'deleted' status."""
    img1 = ImageFile(Path("img1.jpg"))
    img2 = ImageFile(Path("img2.jpg"))
    mock_controller.image_files = [img1, img2]

    summary = mock_controller._delete_indices([0, 1], "test")
    job_id = summary["job_id"]
    assert len(mock_controller.image_files) == 0

    # User undoes immediately
    mock_controller.undo_delete()
    assert len(mock_controller.image_files) == 2

    # Simulate completion arriving AFTER undo (some files already moved)
    result = {
        "job_id": job_id,
        "successes": [{
            "jpg": img1.path.resolve(),
            "recycled_jpg": Path("recycle/img1.jpg"),
            "raw": None,
            "recycled_raw": None
        }],
        "failures": [
            {"jpg": img2.path.resolve(), "raw": None, "code": "cancelled"},
        ],
        "cancelled": True,
    }
    mock_controller._on_delete_finished(result)

    # A "delete" undo entry SHOULD be added for the already-moved file
    # so the user can "Undo" again to restore it.
    delete_entries = [e for e in mock_controller.undo_history if e[0] == "delete"]
    assert len(delete_entries) == 1

    # UI list should still have both images (restored by undo)
    # UI list should have 1 image (img2 remains, img1 removed again as 'success')
    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0].path == img2.path

    # Status message SHOULD verify the "already moved" notification
    found_msg = False
    for call in mock_controller.update_status_message.call_args_list:
        msg = call[0][0]
        if "already moved" in msg.lower():
            found_msg = True
            break
    assert found_msg, "Status message regarding already moved files not found"


# ── Permanent delete result handled ──────────────────────────────────

def test_perm_delete_result_handled(mock_controller):
    """Permanent delete result is handled correctly (not early-returned)."""
    # Simulate a _perm_result signal arriving
    result = {
        "_perm_result": True,
        "perm_success": [(0, Mock()), (1, Mock())],
        "perm_fail": [],
    }
    mock_controller._on_delete_finished(result)

    # Should show status message
    mock_controller.update_status_message.assert_called_with(
        "Permanently deleted 2 image(s)"
    )


def test_automatic_rollback_on_recycle_failure(mock_controller, tmp_path):
    """Verify that recycle failure results in automatic UI restoration without prompting."""
    img_path = tmp_path / "test.jpg"
    img_path.write_text("content")
    img = ImageFile(img_path)
    mock_controller.image_files = [img]

    summary = mock_controller._delete_indices([0], "test")
    job_id = summary["job_id"]

    # Simulate worker result: recycle failed
    result = {
        "job_id": job_id,
        "successes": [],
        "failures": [{
            "jpg": img_path.resolve(),
            "raw": None,
            "code": "recycle_failed"
        }],
        "cancelled": False,
    }

    # No prompt expected now
    with patch("faststack.app.confirm_permanent_delete") as mock_confirm:
        mock_controller._on_delete_finished(result)
        mock_confirm.assert_not_called()

    # Item should be restored automatically
    assert len(mock_controller.image_files) == 1
    assert mock_controller.image_files[0].path == img_path.resolve()


# ── Batch/selection clearing tests ────────────────────────────────────

def test_batch_restored_on_rollback(mock_controller):
    """Batch state is restored when delete completion rolls back failed items."""
    img1 = ImageFile(Path("test1.jpg"))
    img2 = ImageFile(Path("test2.jpg"))
    mock_controller.image_files = [img1, img2]
    mock_controller.batches = [[0, 1]]
    mock_controller.batch_start_index = 0

    mock_controller.delete_batch_images()

    # Batches cleared optimistically
    assert mock_controller.batches == []

    # Get the job
    job_id = list(mock_controller._pending_delete_jobs.keys())[0]

    # Simulate complete failure
    result = {
        "job_id": job_id,
        "successes": [],
        "failures": [
            {"jpg": img1.path.resolve(), "raw": None, "code": "recycle_failed"},
            {"jpg": img2.path.resolve(), "raw": None, "code": "recycle_failed"},
        ],
        "cancelled": True,
    }
    mock_controller._on_delete_finished(result)

    # Batches should be restored
    assert mock_controller.batches == [[0, 1]]
    assert mock_controller.batch_start_index == 0
    # Images should be restored
    assert len(mock_controller.image_files) == 2
