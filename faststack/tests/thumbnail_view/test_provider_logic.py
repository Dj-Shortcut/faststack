"""Tests for _parse_id logic in ThumbnailProvider."""

import pytest
from faststack.thumbnail_view.provider import ThumbnailProvider

class TestProviderLogic:
    @pytest.fixture
    def provider(self):
        p = ThumbnailProvider.__new__(ThumbnailProvider)
        p._default_size = 200
        return p

    def test_parse_id_file_success(self, provider):
        id_str = "256/pathhash123/123456789?r=1&reason=scroll"
        parsed = provider._parse_id(id_str)
        
        assert parsed.id_clean == "256/pathhash123/123456789"
        assert parsed.parts == ["256", "pathhash123", "123456789"]
        assert parsed.thumb_size == 256
        assert parsed.path_hash == "pathhash123"
        assert parsed.mtime_ns == 123456789
        assert parsed.reason == "scroll"
        assert parsed.is_folder is False
        assert parsed.is_valid is True

    def test_parse_id_folder_success(self, provider):
        id_str = "folder/pathhash456/987654321?r=2"
        parsed = provider._parse_id(id_str)
        
        assert parsed.id_clean == "folder/pathhash456/987654321"
        assert parsed.parts == ["folder", "pathhash456", "987654321"]
        assert parsed.thumb_size == 200  # Default size
        assert parsed.path_hash == "pathhash456"
        assert parsed.mtime_ns == 987654321
        assert parsed.reason == "unknown"
        assert parsed.is_folder is True
        assert parsed.is_valid is True

    def test_parse_id_invalid_format(self, provider):
        id_str = "invalid/id"
        parsed = provider._parse_id(id_str)
        
        assert parsed.is_valid is False

    def test_parse_id_invalid_number(self, provider):
        id_str = "abc/pathhash/123"
        parsed = provider._parse_id(id_str)
        
        assert parsed.is_valid is False
