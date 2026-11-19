"""Where data lives. Never inside the repo or OneDrive (non-ASCII path, sync churn)."""
from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "IHALE_DATA_DIR"
USER_AGENT = "ihaleGozlemevi/0.1 (+https://github.com/efebarlas/ihaleGozlemevi)"


def data_dir() -> Path:
    """Data root: $IHALE_DATA_DIR, else ~/ihaleGozlemevi-data.

    Not %LOCALAPPDATA%: inside the packaged Claude desktop app, AppData writes are
    silently redirected to the app's private package folder, so runs from the app and
    from Task Scheduler would see different data. The profile root is not redirected
    and is not synced by OneDrive.
    """
    override = os.environ.get(ENV_VAR)
    root = Path(override) if override else Path.home() / "ihaleGozlemevi-data"
    return root.expanduser().resolve()


def bulletins_dir() -> Path:
    return data_dir() / "bulletins"


def db_path() -> Path:
    return data_dir() / "ihale.db"
