"""Where data lives. Never inside the repo or OneDrive (non-ASCII path, sync churn)."""
from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "IHALE_DATA_DIR"
USER_AGENT = "ihaleGozlemevi/0.1 (+https://github.com/efebarlas/ihaleGozlemevi)"


def data_dir() -> Path:
    """Data root: $IHALE_DATA_DIR, else LOCALAPPDATA/ihaleGozlemevi (~/.local/share fallback)."""
    override = os.environ.get(ENV_VAR)
    if override:
        root = Path(override)
    else:
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) / "ihaleGozlemevi" if base else Path.home() / ".local" / "share" / "ihaleGozlemevi"
    return root.expanduser().resolve()


def bulletins_dir() -> Path:
    return data_dir() / "bulletins"


def db_path() -> Path:
    return data_dir() / "ihale.db"
