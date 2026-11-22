"""Where data lives. Never inside the repo or OneDrive (non-ASCII path, sync churn).

Resolution order:
1. `$IHALE_DATA_DIR`
2. the pointer file `~/.ihaleGozlemevi-data-dir` (one line: the data path)
3. `~/ihaleGozlemevi-data`

Not %LOCALAPPDATA%: inside the packaged Claude desktop app, AppData writes are silently
redirected to the app's private package folder, so runs from the app and from Task Scheduler
would see different data. The profile root (home of the pointer file) is not redirected.

**Missing-data guard.** If the resolved folder does not exist (e.g. the external SSD is
unplugged), or exists but holds no `ihale.db`, `data_dir()` raises `DataDirMissing`. The run
then fails loudly and does nothing. It never creates an empty data dir, re-downloads
everything, or deploys an empty site. A brand-new install sets `IHALE_ALLOW_NEW_DATA_DIR=1`
once.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "IHALE_DATA_DIR"
ALLOW_NEW_ENV = "IHALE_ALLOW_NEW_DATA_DIR"
POINTER_FILE = Path.home() / ".ihaleGozlemevi-data-dir"
USER_AGENT = "ihaleGozlemevi/0.1 (+https://github.com/efebarlas/ihaleGozlemevi)"


class DataDirMissing(RuntimeError):
    """The configured data dir (or its ihale.db) is missing. Do nothing; tell a human."""


def _configured() -> tuple[Path, str]:
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override), f"${ENV_VAR}"
    try:
        pointed = POINTER_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        pointed = ""
    if pointed:
        return Path(pointed), f"pointer file {POINTER_FILE}"
    return Path.home() / "ihaleGozlemevi-data", "default"


def data_dir() -> Path:
    root, source = _configured()
    root = root.expanduser()
    if os.environ.get(ALLOW_NEW_ENV) == "1":
        return root.resolve()
    if not root.is_dir():
        raise DataDirMissing(
            f"data dir {root} (from {source}) does not exist. Is the external drive plugged in? "
            f"Nothing was done. Set {ALLOW_NEW_ENV}=1 only for a deliberate fresh install.")
    if not (root / "ihale.db").is_file():
        raise DataDirMissing(
            f"data dir {root} (from {source}) has no ihale.db. Refusing to start from an empty store. "
            f"Set {ALLOW_NEW_ENV}=1 only for a deliberate fresh install.")
    return root.resolve()


def bulletins_dir() -> Path:
    return data_dir() / "bulletins"


def db_path() -> Path:
    return data_dir() / "ihale.db"
