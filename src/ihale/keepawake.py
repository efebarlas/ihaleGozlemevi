"""Keep Windows from sleeping while a long job runs (no admin, no power-plan change).

Holds ES_CONTINUOUS | ES_SYSTEM_REQUIRED on the calling thread for the life of the `with` block and clears it
(ES_CONTINUOUS alone) on exit, including on error. The request is per thread: use it from the main thread that
runs the job. A no-op off Windows or when the call fails (never breaks the job).
"""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

log = logging.getLogger("ihale.keepawake")


def _set(flags: int) -> int:
    import ctypes
    fn = ctypes.windll.kernel32.SetThreadExecutionState
    fn.argtypes = [ctypes.c_uint]
    fn.restype = ctypes.c_uint
    return fn(flags)


@contextmanager
def keep_awake():
    held = False
    if sys.platform == "win32":
        try:
            held = bool(_set(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
        except Exception as e:  # noqa: BLE001
            log.warning("keep-awake not set: %s", e)
    try:
        yield held
    finally:
        if held:
            try:
                _set(ES_CONTINUOUS)
            except Exception:  # noqa: BLE001
                pass
