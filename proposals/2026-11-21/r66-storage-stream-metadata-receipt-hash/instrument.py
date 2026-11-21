#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
source = Path("storage/session-storage/src/metadata.rs")
legacy = subprocess.check_output(
    ["git", "show", f"HEAD:{source}"], cwd=root, text=True
)
assert subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=root, text=True
).strip() == "9469e3b12529d08b1f4a76882693e2065e842c51"
start = "pub(crate) fn compare_exchange("
assert legacy.count(start) == 1
old = legacy[legacy.index(start):].replace(start, "fn legacy_compare_exchange(", 1)
probe = Path(__file__).with_name("cas-probe.rs").read_text()
with (root / source).open("a") as f:
    f.write("\n#[cfg(test)]\nmod r66_probe {\n" + probe + "\n" + old + "\n}\n")
