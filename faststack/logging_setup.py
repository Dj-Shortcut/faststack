"""Configures application-wide logging."""

import logging
import logging.handlers
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def _is_writable_directory(path: Path) -> bool:
    """Return True when the directory exists and a temp file can be created there."""
    try:
        if not path.exists() or not path.is_dir():
            return False
        with NamedTemporaryFile(dir=path, prefix=".faststack-write-test-", delete=True):
            pass
        return True
    except OSError:
        return False


def get_app_data_dir() -> Path:
    """Returns the application data directory."""
    candidates = []

    app_data = os.getenv("APPDATA")
    if app_data:
        candidates.append(Path(app_data) / "faststack")

    candidates.append(Path.home() / ".faststack")

    for candidate in candidates:
        if _is_writable_directory(candidate):
            return candidate
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if _is_writable_directory(candidate):
            return candidate

    return Path.home() / ".faststack"


def setup_logging(debug: bool = False):
    """Sets up logging to a rotating file in the app data directory.

    Args:
        debug: If True, sets log level to DEBUG. Otherwise, sets to WARNING to reduce noise.
    """
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console handler (for seeing logs in terminal)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Set log level based on debug flag
    root_logger.setLevel(logging.DEBUG if debug else logging.WARNING)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    try:
        log_dir = get_app_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError as exc:
        root_logger.warning("File logging disabled: %s", exc)

    # Configure logging for key modules
    if debug:
        logging.getLogger("faststack.imaging.cache").setLevel(logging.DEBUG)
        logging.getLogger("faststack.imaging.prefetch").setLevel(logging.DEBUG)
    else:
        # In non-debug mode, only log errors from these noisy modules
        logging.getLogger("faststack.imaging.cache").setLevel(logging.ERROR)
        logging.getLogger("faststack.imaging.prefetch").setLevel(logging.ERROR)
    logging.getLogger("PIL").setLevel(logging.INFO)
