from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback

from PySide6.QtWidgets import QApplication

from cyberflash import __app_name__, __version__
from cyberflash.services.config_service import ConfigService
from cyberflash.ui.main_window import FramelessMainWindow
from cyberflash.ui.themes.theme_engine import ThemeEngine
from cyberflash.utils.platform_utils import get_app_data_dir

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _setup_logging(config: ConfigService) -> None:
    """Configure console + rotating-file logging."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler — always present
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG)
    console.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(console)

    # File handler — optional, defaults to enabled
    if config.get_bool("logging/file_enabled"):
        log_dir = get_app_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "cyberflash.log"

        max_bytes = config.get_int("logging/max_file_size_mb") * 1024 * 1024
        backup_count = config.get_int("logging/backup_count")

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(file_handler)

        logger.info("Log file: %s", log_file)


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    logger.error(
        "Unhandled exception:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    )
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main() -> None:
    config = ConfigService()

    _setup_logging(config)

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__app_name__)
    # Qt 6: high-DPI scaling is always enabled, no attribute needed

    theme = config.get_str("theme") or "cyber_dark"
    ThemeEngine.apply_theme(theme, app)

    window = FramelessMainWindow()
    window.setWindowTitle(__app_name__)
    window.show()

    sys.exit(app.exec())
