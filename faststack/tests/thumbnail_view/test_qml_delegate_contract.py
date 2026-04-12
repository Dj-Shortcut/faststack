"""Contract tests between ThumbnailModel roles and ThumbnailTile QML."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from faststack.thumbnail_view.folder_stats import FolderStats
from faststack.thumbnail_view.model import ThumbnailEntry, ThumbnailModel


@pytest.fixture(scope="module")
def qapp():
    """Ensure a Qt core app exists for model instances."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    yield app


def _thumbnail_tile_required_properties() -> set[str]:
    qml_path = Path(__file__).resolve().parents[2] / "qml" / "ThumbnailTile.qml"
    qml_text = qml_path.read_text(encoding="utf-8")
    return set(
        re.findall(r"^ {4}required property \w+ (\w+)", qml_text, flags=re.MULTILINE)
    )


def _role_ids_by_name(model: ThumbnailModel) -> dict[str, int]:
    return {name.decode("utf-8"): role for role, name in model.roleNames().items()}


def test_thumbnail_tile_required_roles_exist_on_model(tmp_path, qapp):
    """Every required ThumbnailTile delegate role should be defined by the model."""
    model = ThumbnailModel(
        base_directory=tmp_path,
        current_directory=tmp_path,
        get_metadata_callback=None,
    )

    required_props = _thumbnail_tile_required_properties()
    # `index` is injected by GridView itself, not by ThumbnailModel.roleNames().
    required_model_roles = required_props - {"index"}

    model_role_names = set(_role_ids_by_name(model))
    missing_roles = required_model_roles - model_role_names

    assert missing_roles == set()


def test_thumbnail_tile_required_roles_have_values_for_all_entry_kinds(tmp_path, qapp):
    """Image, folder, and synthetic parent rows should all satisfy delegate requirements."""
    model = ThumbnailModel(
        base_directory=tmp_path,
        current_directory=tmp_path,
        get_metadata_callback=None,
    )

    folder_stats = FolderStats(
        total_images=4,
        stacked_count=1,
        uploaded_count=2,
        edited_count=1,
        jpg_count=3,
        raw_count=1,
        coverage_buckets=[(1.0, 0.5, 0.25, 0.0)],
    )
    parent_entry = ThumbnailEntry(
        path=tmp_path.parent,
        name="..",
        is_folder=True,
        mtime_ns=0,
    )
    folder_entry = ThumbnailEntry(
        path=tmp_path / "child",
        name="child",
        is_folder=True,
        folder_stats=folder_stats,
        mtime_ns=123,
    )
    image_entry = ThumbnailEntry(
        path=tmp_path / "photo.jpg",
        name="photo.jpg",
        is_folder=False,
        is_stacked=True,
        is_uploaded=True,
        is_edited=True,
        is_restacked=True,
        is_favorite=True,
        is_todo=True,
        has_backups=True,
        has_developed=True,
        mtime_ns=456,
    )
    model._entries = [parent_entry, folder_entry, image_entry]

    role_ids = _role_ids_by_name(model)
    required_props = _thumbnail_tile_required_properties() - {"index"}

    for row in range(len(model._entries)):
        index = model.index(row, 0)
        for role_name in required_props:
            value = model.data(index, role_ids[role_name])
            assert value is not None, f"row {row} missing value for role {role_name}"

    image_folder_stats = model.data(model.index(2, 0), role_ids["folderStats"])
    assert image_folder_stats == {
        "total_images": 0,
        "stacked_count": 0,
        "uploaded_count": 0,
        "edited_count": 0,
        "jpg_count": 0,
        "raw_count": 0,
        "coverage_buckets": [],
    }
