"""QML Image Provider for thumbnail grid view."""

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import faststack.util.thumb_debug as thumb_debug

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPixmap, QColor
from PySide6.QtQuick import QQuickImageProvider

from faststack.io.utils import compute_path_hash
from faststack.models import DecodedImage

if TYPE_CHECKING:
    from faststack.thumbnail_view.model import ThumbnailModel
    from faststack.thumbnail_view.prefetcher import ThumbnailPrefetcher, ThumbnailCache

log = logging.getLogger(__name__)

# Placeholder colors
PLACEHOLDER_COLOR = QColor(60, 60, 60)  # Neutral gray for loading
FOLDER_COLOR = QColor(80, 80, 80)  # Slightly different for folders
ERROR_COLOR = QColor(80, 40, 40)  # Dark red for errors


class ThumbnailProvider(QQuickImageProvider):
    """QML Image Provider for thumbnails.

    Non-blocking O(1) implementation:
    - Returns cached pixmap if available
    - Returns placeholder immediately if not cached
    - Schedules decode via prefetcher (does NOT decode inline)

    URL format:
    - Files: image://thumbnail/{size}/{path_hash}/{mtime_ns}?r={rev}
    - Folders: image://thumbnail/folder/{path_hash}/{mtime_ns}?r={rev}
    """

    def __init__(
        self,
        cache: "ThumbnailCache",
        prefetcher: "ThumbnailPrefetcher",
        path_resolver: callable = None,
        default_size: int = 200,
        debug_timing: bool = False,
        debug_trace: bool = False,
    ):
        """Initialize the provider.

        Args:
            cache: Thumbnail cache to read from
            prefetcher: Prefetcher to schedule decodes
            path_resolver: Function to resolve path_hash to actual Path
            default_size: Default thumbnail size
            debug_timing: Enable [THUMB-TIMING] log lines
            debug_trace: Enable verbose trace logs
        """
        super().__init__(QQuickImageProvider.ImageType.Pixmap)
        self._cache = cache
        self._prefetcher = prefetcher
        self._path_resolver = path_resolver
        self._default_size = default_size
        self._debug_timing = debug_timing
        self._debug_trace = debug_trace

        # Pre-create placeholder pixmaps
        self._placeholder = self._create_placeholder(default_size, PLACEHOLDER_COLOR)
        self._folder_placeholder = self._create_folder_placeholder(default_size)
        self._error_placeholder = self._create_placeholder(default_size, ERROR_COLOR)

        # Timing stats for requestPixmap
        self._first_request_time: Optional[float] = None
        self._request_count = 0
        self._first_second_logged = False
        self._first_hit_logged = False

        log.debug("ThumbnailProvider initialized with default size %d", default_size)

    def _create_placeholder(self, size: int, color: QColor) -> QPixmap:
        """Create a solid color placeholder pixmap."""
        pixmap = QPixmap(size, size)
        pixmap.fill(color)
        return pixmap

    def _create_folder_placeholder(self, size: int) -> QPixmap:
        """Create a folder icon placeholder."""
        from PySide6.QtGui import QPainter, QPen, QBrush

        pixmap = QPixmap(size, size)
        pixmap.fill(FOLDER_COLOR)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a simple folder shape
        pen = QPen(QColor(150, 150, 150))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(100, 100, 100)))

        # Folder body
        margin = size // 6
        tab_width = size // 3
        tab_height = size // 8

        # Tab at top
        painter.drawRect(
            margin,
            margin + tab_height,
            size - 2 * margin,
            size - 2 * margin - tab_height,
        )

        # Tab extension
        painter.fillRect(
            margin, margin, tab_width, tab_height + 2, QColor(100, 100, 100)
        )

        painter.end()
        return pixmap

    def requestPixmap(self, id_str: str, size: QSize, requestedSize: QSize) -> QPixmap:
        """Request a pixmap for the given ID.

        This method is O(1) - returns immediately with cached data or placeholder.

        Args:
            id_str: URL path after "image://thumbnail/"
            size: Output size reference (set by us)
            requestedSize: Requested size from QML

        Returns:
            QPixmap of the thumbnail or placeholder
        """
        # Parse the ID
        # Format: {size}/{path_hash}/{mtime_ns}?r={rev}
        # Or: folder/{path_hash}/{mtime_ns}?r={rev}

        # Strip query params
        id_clean = id_str.split("?")[0]
        
        # Track total requests if logging enabled
        if thumb_debug.timing_enabled or thumb_debug.trace_enabled:
            thumb_debug.inc_request_count()

        # Deferred logging setup
        timer = None
        if thumb_debug.timing_enabled or thumb_debug.trace_enabled:
            # Parse reason
            reason = "unknown"
            parts_query = id_str.split("?")
            if len(parts_query) > 1:
                query = parts_query[1]
                for param in query.split("&"):
                    if param.startswith("reason="):
                        reason = param.split("=")[1]
            
            # Key/ID parts
            # Key format: {size}/{path_hash}/{mtime_ns}
            parts = id_clean.split("/")
            if len(parts) < 3:
                log.debug("Invalid thumbnail ID format: %s", id_str)
                return self._error_placeholder

            # Determine if folder (early exit for folders)
            if parts[0] == "folder":
                return self._folder_placeholder

            try:
                thumb_size = int(parts[0])
                path_hash = parts[1]
                mtime_ns = int(parts[2])
            except (ValueError, IndexError):
                log.debug("Invalid thumbnail ID: %s", id_str)
                return self._error_placeholder

            cache_key = f"{thumb_size}/{path_hash}/{mtime_ns}"
            # Resolve path only if needed for trace
            path = self._path_resolver(path_hash) if self._path_resolver else None
            timer = thumb_debug.ThumbTimer(key=cache_key, path=path, reason=reason)
            thumb_debug.log_trace("requested", rid=timer.rid, key=timer.key, src=timer.src, reason=reason)
        else:
            # Normal fast path — already have id_clean
            cache_key = id_clean

        # Check cache (O(1) lookup)
        t_cache_get_start = time.perf_counter()
        cached_bytes = self._cache.get(cache_key)
        dt_cache_get = (time.perf_counter() - t_cache_get_start) * 1000
        
        if cached_bytes:
            if timer:
                thumb_debug.inc("req_cache_hit")
                thumb_debug.log_trace("cache_hit", rid=timer.rid, ms=f"{dt_cache_get:.3f}")
            
            # Decode JPEG bytes to pixmap
            t_pixmap_start = time.perf_counter()
            pixmap = self._bytes_to_pixmap(cached_bytes)
            dt_pixmap = (time.perf_counter() - t_pixmap_start) * 1000

            if pixmap and not pixmap.isNull():
                if timer:
                    thumb_debug.log_trace("delivered", rid=timer.rid, pixmap_ms=f"{dt_pixmap:.3f}")
                    timer.log_timing(
                        cache="hit", 
                        cache_get_ms=f"{dt_cache_get:.3f}",
                        pixmap_ms=f"{dt_pixmap:.3f}"
                    )
                return pixmap
        
        if timer:
            thumb_debug.inc("req_cache_miss")
            thumb_debug.log_trace("cache_miss", rid=timer.rid, ms=f"{dt_cache_get:.3f}")

        # Not in cache - parse parts if we haven't already
        # If timer was created, parts, thumb_size, path_hash, mtime_ns are already set.
        # If not, we need to parse them now.
        if not timer:
            parts = id_clean.split("/")
            if len(parts) < 3:
                log.debug("Invalid thumbnail ID format: %s", id_str)
                return self._error_placeholder

            # Determine if folder (early exit for folders)
            if parts[0] == "folder":
                path_hash = parts[1]
                try:
                    mtime_ns = int(parts[2])
                except ValueError:
                    return self._error_placeholder
                return self._folder_placeholder

            try:
                thumb_size = int(parts[0])
                path_hash = parts[1]
                mtime_ns = int(parts[2])
            except (ValueError, IndexError):
                log.debug("Invalid thumbnail ID: %s", id_str)
                return self._error_placeholder

        # Resolve path
        path = self._path_resolver(path_hash) if self._path_resolver else None
        if path:
            self._prefetcher.submit(
                path, mtime_ns, thumb_size, 
                priority=self._prefetcher.PRIO_HIGH,
                timer=timer
            )

        # Return placeholder immediately (non-blocking)
        return self._placeholder

    def _bytes_to_pixmap(self, jpeg_bytes: bytes) -> Optional[QPixmap]:
        """Convert JPEG bytes to QPixmap."""
        try:
            qimage = QImage()
            if qimage.loadFromData(jpeg_bytes, "JPEG"):
                return QPixmap.fromImage(qimage)
        except Exception as e:
            log.debug("Failed to convert bytes to pixmap: %s", e)
        return None


class PathResolver:
    """Resolves path hashes back to actual paths.

    Maintains a mapping from hash -> path for the current directory.
    """

    def __init__(self):
        self._hash_to_path: dict = {}

    def register(self, path: Path, path_hash: str):
        """Register a path with its hash."""
        self._hash_to_path[path_hash] = path

    def resolve(self, path_hash: str) -> Optional[Path]:
        """Resolve a hash to its path."""
        return self._hash_to_path.get(path_hash)

    def clear(self):
        """Clear all registered paths."""
        self._hash_to_path.clear()

    def update_from_model(self, model: "ThumbnailModel"):
        """Update registrations from a ThumbnailModel."""
        self.clear()

        t0 = time.perf_counter()

        # Optimized update using fast string hashing (no filesystem calls)
        for i in range(model.rowCount()):
            entry = model.get_entry(i)
            if entry and not entry.is_folder:
                # Use centralized hash helper to ensure match with ThumbnailModel
                path_hash = compute_path_hash(entry.path)
                self._hash_to_path[path_hash] = entry.path

        dt = time.perf_counter() - t0
        log.debug(f"PathResolver update took {dt*1000:.2f}ms for {model.rowCount()} items")
