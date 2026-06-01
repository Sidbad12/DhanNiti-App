"""
DhanNiti — Centralized Logging Configuration
Sets up a single root logger that writes to both console and a rotating log file.
Import and call `setup_logging()` from any entry point (main.py, backfill, API server).
"""

import logging
import logging.handlers
import os
from datetime import datetime

# NumPy 2.0 Compatibility Patch for SHAP / older ML libraries
try:
    import numpy as np
    if not hasattr(np, "obj2sctype"):
        def obj2sctype(rep, default=None):
            try:
                return np.dtype(rep).type
            except Exception:
                return default
        np.obj2sctype = obj2sctype
except ImportError:
    pass

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "dhanniti.log")


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configure the root logger with:
    - Console handler (colored, concise)
    - Rotating file handler (full detail, max 10MB, keeps 7 backups)

    Returns the root logger so callers can immediately use it.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    root_logger = logging.getLogger()

    # Avoid duplicate handlers if setup_logging() is called multiple times
    if root_logger.handlers:
        return root_logger

    root_logger.setLevel(level)

    # ── File handler (rotating, full format) ─────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=7,               # Keep last 7 log files (70 MB total)
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Capture everything to file
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # ── Console handler (concise, human-readable) ─────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    ))

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    root_logger.info(f"Logger initialised — writing to {os.path.abspath(LOG_FILE)}")
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Shortcut: get a named child logger (after setup_logging() has been called)."""
    return logging.getLogger(name)
