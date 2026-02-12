import pytest
import os
from unittest.mock import MagicMock, call, patch
from pathlib import Path

from faststack.app import AppController
from faststack.models import ImageFile

@pytest.fixture
def mock_app():
    """Create a partial mock of AppController for deletion testing."""
    with patch("faststack.app.ByteLRUCache") as MockCache, \
         patch("faststack.app.ThumbnailModel") as MockModel, \
         patch("faststack.app.Prefetcher") as MockPrefetcher, \
         patch("faststack.app.PathResolver") as MockResolver, \
         patch("faststack.app.Watcher"), \
         patch("faststack.app.uuid"), \
         patch("faststack.app.QTimer"), \
         patch("faststack.app.concurrent.futures.ThreadPoolExecutor"):
        
        # Pass mock engine
        mock_engine = MagicMock()
        app = AppController(Path("."), mock_engine)
        app.image_cache = MagicMock()
        app.prefetcher = MagicMock()
        app._thumbnail_model = MagicMock()
        app._path_resolver = MagicMock()
        app._path_to_index = {}
        app.sidecar = MagicMock()
        
        # Mock PathResolver update to verify no resolve calls
        return app

def test_delete_uses_targeted_eviction(mock_app):
    """Verify delete_indices calls evict_paths and NOT clear."""
    # Setup
    img1 = ImageFile(Path("c:/images/img1.jpg"), raw_pair=Path("c:/images/img1.CR2"))
    img2 = ImageFile(Path("c:/images/img2.jpg"))
    mock_app.image_files = [img1, img2]
    mock_app._path_to_index = {
        mock_app._key(img1.path): 0,
        mock_app._key(img2.path): 1
    }
    mock_app.current_index = 0
    mock_app.display_generation = 10
    
    # Mock deletion executor
    mock_app._delete_executor = MagicMock()
    mock_app._delete_executor.submit.return_value = MagicMock()
    
    # Act
    # indices to delete: [0] (img1)
    summary = mock_app._delete_indices([0], "test")
    
    # Assert
    # 1. Should not clear entire cache
    mock_app.image_cache.clear.assert_not_called()
    
    # 2. Should not bump display generation
    assert mock_app.display_generation == 10
    
    # 3. Should call evict_paths with correct paths
    # Note: unordered check because implementation might vary order
    mock_app.image_cache.evict_paths.assert_called_once()
    args, _ = mock_app.image_cache.evict_paths.call_args
    evicted = args[0]
    assert len(evicted) == 2
    assert img1.path in evicted
    assert img1.raw_pair in evicted
    
    # 4. Should cancel prefetch
    mock_app.prefetcher.cancel_all.assert_called_once()

def test_evict_paths_windows_handling():
    """Verify ByteLRUCache.evict_paths handles Windows paths correctly."""
    from faststack.imaging.cache import ByteLRUCache
    
    # Create a real cache instance (mocking LRUCache methods if needed, but ByteLRUCache is simple)
    # Pass a simple size_of function to avoid dependency on get_decoded_image_size
    cache = ByteLRUCache(1000, size_of=lambda x: 1)
    
    # Add entries with forward slashes (as build_cache_key does)
    key1 = "C:/images/img1.jpg::0"
    key2 = "C:/images/img1.jpg::1"  # Different generation
    key3 = "C:/images/img2.jpg::0"  # Keep this
    
    cache[key1] = 1
    cache[key2] = 1
    cache[key3] = 1
    
    # Act: Evict using Windows-style path string
    win_path = "C:\\images\\img1.jpg"
    cache.evict_paths([win_path])
    
    # Assert
    assert key1 not in cache
    assert key2 not in cache
    assert key3 in cache
    
    # Act: Evict using Path object
    path_obj = Path("C:/images/img2.jpg")
    cache.evict_paths([path_obj])
    
    # Assert
    assert key3 not in cache

def test_model_hashing_no_resolve():
    """Verify PathResolver and ThumbnailModel do NOT call resolve()."""
    from faststack.thumbnail_view.model import ThumbnailModel
    from faststack.thumbnail_view.provider import PathResolver
    from faststack.models import ImageFile as ModelImageFile
    
    # Mock Path.resolve to raise exception
    with patch("faststack.io.utils.Path.resolve", side_effect=Exception("Should not call resolve!")):
        with patch("faststack.thumbnail_view.model.Path.resolve", side_effect=Exception("Should not call resolve!")):
             # Note: we need to patch wherever usage might occur or globally.
             # Since we changed code to NOT use it, calling the methods should be safe.
             
             # Test Helper directly
             from faststack.io.utils import compute_path_hash
             p = Path("c:/foo/bar.jpg")
             # This should NOT fail
             h = compute_path_hash(p)
             assert len(h) == 16
             
             # Test Resolver update
             resolver = PathResolver()
             model = MagicMock()
             model.rowCount.return_value = 1
             entry = MagicMock()
             entry.path = p
             entry.is_folder = False
             model.get_entry.return_value = entry
             
             resolver.update_from_model(model)
             # Should succeed and have entry
             assert len(resolver._hash_to_path) == 1
