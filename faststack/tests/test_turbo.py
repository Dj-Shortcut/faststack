import importlib
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_create_turbojpeg_uses_explicit_env_path(monkeypatch):
    turbo = importlib.import_module("faststack.imaging.turbo")

    calls = []

    def fake_decoder(path=None):
        calls.append(path)
        if path is None:
            raise RuntimeError("default load failed")
        if path == "C:/turbo/bin/turbojpeg.dll":
            return SimpleNamespace(source=path)
        raise RuntimeError("unexpected path")

    monkeypatch.setattr(turbo, "TurboJPEG", fake_decoder)
    monkeypatch.setenv("FASTSTACK_TURBOJPEG_LIB", "C:/turbo/bin/turbojpeg.dll")

    decoder, available = turbo.create_turbojpeg()

    assert available is True
    assert decoder.source == "C:/turbo/bin/turbojpeg.dll"
    assert calls == [None, "C:/turbo/bin/turbojpeg.dll"]


def test_create_turbojpeg_logs_failed_candidates(monkeypatch, caplog):
    turbo = importlib.import_module("faststack.imaging.turbo")

    def fake_decoder(path=None):
        raise RuntimeError(f"boom:{path}")

    monkeypatch.setattr(turbo, "TurboJPEG", fake_decoder)
    monkeypatch.setattr(
        turbo,
        "_candidate_library_paths",
        lambda: ["C:/one/turbojpeg.dll", "C:/two/turbojpeg.dll"],
    )

    with caplog.at_level(logging.WARNING):
        decoder, available = turbo.create_turbojpeg()

    assert decoder is None
    assert available is False
    assert "C:/one/turbojpeg.dll" in caplog.text
    assert "C:/two/turbojpeg.dll" in caplog.text
    assert "Falling back to Pillow" in caplog.text


def test_get_app_data_dir_falls_back_when_appdata_is_not_creatable(monkeypatch, tmp_path):
    logging_setup = importlib.import_module("faststack.logging_setup")

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    fallback_dir = home_dir / ".faststack"
    fallback_dir.mkdir()

    blocked_root = tmp_path / "blocked"
    appdata_target = blocked_root / "faststack"

    original_mkdir = Path.mkdir

    def fake_mkdir(self, *args, **kwargs):
        if self == appdata_target:
            raise OSError("nope")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setenv("APPDATA", str(blocked_root))
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    assert logging_setup.get_app_data_dir() == fallback_dir


def test_is_writable_directory_does_not_create_missing_dir(tmp_path):
    logging_setup = importlib.import_module("faststack.logging_setup")

    missing = tmp_path / "missing"

    assert logging_setup._is_writable_directory(missing) is False
    assert missing.exists() is False


def test_setup_logging_keeps_console_handler_when_file_logging_fails(monkeypatch):
    logging_setup = importlib.import_module("faststack.logging_setup")

    monkeypatch.setattr(logging_setup, "get_app_data_dir", lambda: Path("/bad-path"))
    monkeypatch.setattr(
        logging_setup.logging.handlers,
        "RotatingFileHandler",
        Mock(side_effect=OSError("disk full")),
    )

    logging_setup.setup_logging(debug=True)

    root_logger = logging.getLogger()
    try:
        assert any(
            isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers
        )
    finally:
        root_logger.handlers.clear()
