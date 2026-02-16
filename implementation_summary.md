The implementation for optimizing startup and grid loading has been completed and refined based on review.

**Summary of Changes:**

1.  **`faststack/thumbnail_view/model.py`**:
    *   Updated `set_filter` and `set_filter_flags` to accept a `refresh=False` parameter, enabling batched updates without immediate repainting.

2.  **`faststack/app.py`**:
    *   **Startup & Grid Loading**: Added `_grid_model_dirty` flag and `_grid_refreshes` / `_scan_count_variant` counters to control refresh logic efficiently.
    *   **`refresh_image_list`**: Optimized to only refresh the grid model if the grid is currently active. Otherwise, it marks the model as dirty.
    *   **`load`**: ensuring exactly one disk scan and one model refresh occur during startup. Explicitly manages `_grid_model_dirty` and ensures grid model population if starting in grid mode *only if* the model is empty, preventing double refreshes. Removed unused `_scan_count_simple` counter.
    *   **`apply_filter` / `clear_filter`**:
        *   Updates the cached list first.
        *   Updates model filter parameters silently.
        *   Cancels thumbnail prefetch jobs *only* if grid view is active.
        *   Only triggers `refresh_from_controller` if grid view is active. Otherwise, marks model as dirty.
        *   **Safety**: Added explicit checks for `self._thumbnail_model` before calling methods on it, preventing potential crashes if the model is not initialized.
    *   **`_set_grid_view_active`**:
        *   Removed fallback to `refresh()` (disk scan) and unnecessary `image_files` check. Now consistently uses `refresh_from_controller` (memory refresh) ensuring predictable performance.
    *   **`refresh_grid`**: Updated docstring to explicitly state this performs a full disk rescan.

**Verification:**

*   **Tests**: `faststack/tests/test_startup_optimization.py` confirms:
    *   **Startup**: Exactly one disk scan and one grid refresh occur on load.
    *   **Filtering**: Filter application triggers a single refresh_from_controller call (no disk scan) only when grid is active.
    *   **Inactive Grid**: Changes while grid is inactive correctly mark the model as dirty without triggering immediate refreshes.
