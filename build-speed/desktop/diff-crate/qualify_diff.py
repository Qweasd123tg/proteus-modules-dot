#!/usr/bin/env python3
"""Fixed diff library qualification; no component or target CLI selector."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from pure_crate import inspect_output, main, validate_expected


if __name__ == "__main__":
    raise SystemExit(main(HERE / "expected.json", Path(__file__)))
