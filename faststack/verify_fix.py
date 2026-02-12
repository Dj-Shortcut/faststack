import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Mock PySide6 BEFORE importing anything from faststack
qt_mock = Mock()
qt_mock.ItemDataRole.UserRole = 0x100
sys.modules['PySide6'] = Mock()
sys.modules['PySide6.QtCore'] = Mock()
sys.modules['PySide6.QtCore'].Qt = qt_mock
sys.modules['PySide6.QtCore'].QAbstractListModel = Mock
sys.modules['PySide6.QtCore'].QModelIndex = Mock
sys.modules['PySide6.QtCore'].QThread = Mock
sys.modules['PySide6.QtCore'].Signal = Mock
sys.modules['PySide6.QtCore'].Slot = Mock

# Mock other PyQt/PySide modules as well to be safe
sys.modules['PySide6.QtGui'] = Mock()
sys.modules['PySide6.QtWidgets'] = Mock()
sys.modules['PySide6.QtQml'] = Mock()

# Add project root (parent of faststack package) to sys.path
sys.path.append(r'C:\code\faststack')

# Now import the model
with patch('faststack.io.indexer.find_images', return_value=[]):
    from faststack.thumbnail_view.model import ThumbnailModel
    
    # Mock QThread.currentThread() and self.thread() to avoid mismatch assert
    with patch('PySide6.QtCore.QThread.currentThread', return_value=1):
        model = ThumbnailModel(Path('.'), Path('.'))
        model.thread = Mock(return_value=1)
        model.beginResetModel = Mock()
        model.endResetModel = Mock()
        model.selectionChanged = Mock()
        model._add_folders_to_entries = Mock()
        model._add_images_to_entries = Mock()
        model._rebuild_id_mapping = Mock()
        
        # Ensure data structures used by method logic are real
        model._entries = []
        model._id_to_row = {}
        model._selected_indices = set()
        
        print("Testing refresh()...")
        try:
            model.refresh()
            print("refresh() passed (no NameError)")
        except NameError as e:
            print(f"refresh() failed with NameError: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"refresh() failed with unexpected error: {e}")
            
        print("Testing refresh_from_controller()...")
        try:
            model.refresh_from_controller([], metadata_map={})
            print("refresh_from_controller() passed (no NameError)")
        except NameError as e:
            print(f"refresh_from_controller() failed with NameError: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"refresh_from_controller() failed with unexpected error: {e}")

print("Verification complete.")
