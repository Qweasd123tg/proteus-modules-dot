#!/usr/bin/env python3
"""Add a stock inventory oracle and a test-only probe to a disposable patched checkout."""
import argparse
import subprocess
from pathlib import Path

BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
FILE = "storage/session-storage/src/service/catalog/durable.rs"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repository", type=Path, help="Git checkout containing the original exact base")
p.add_argument("candidate", type=Path, help="disposable directory with the candidate already applied")
a = p.parse_args()
target = a.candidate / FILE
new = target.read_text()
old = subprocess.check_output(["git", "-C", a.repository, "show", f"{BASE}:{FILE}"], text=True)
start = old.index("pub(in crate::service) fn blob_stamps(")
end = old.index("/// Keep only", start)
stock = old[start:end].replace("pub(in crate::service) fn blob_stamps(", "fn stock(")
assert "#[cfg(test)]\nmod r47_inventory_probe" not in new
probe = (Path(__file__).parent / "inventory_probe.rs").read_text()
target.write_text(new + "\n#[cfg(test)]\nmod r47_inventory_probe {\nuse super::*;\n" + stock + probe + "}\n")
