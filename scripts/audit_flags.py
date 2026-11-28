"""M5-audit: independent flag checker (core in src/ihale/audit.py). Same as `ihale audit`.

    .venv/Scripts/python.exe -X utf8 scripts/audit_flags.py [--db PATH] [--json OUT]

Exit 0 = no mismatches, 8 = mismatches (the informational lists never count).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ihale.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["audit", *sys.argv[1:]]))
