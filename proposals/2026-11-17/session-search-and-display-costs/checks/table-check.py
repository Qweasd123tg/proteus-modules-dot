"""Build the bounded plain-text table probe against the matching two source trees."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv) != 3:
    raise SystemExit("usage: python3 table-check.py BASE_CORE_TREE PATCHED_CORE_TREE")
path = Path("crates/proteus-core/src/core/topology_render/table.rs")
probe = Path(__file__).resolve().with_name("table-probe.rs")
outputs = []
with tempfile.TemporaryDirectory() as tmp:
    for label, root in zip(("before", "after"), sys.argv[1:]):
        exe = Path(tmp) / label
        env = dict(os.environ, TABLE_RS=str((Path(root)/path).resolve()))
        subprocess.run(["rustc", "--edition", "2024", "-O", "-D", "warnings", str(probe), "-o", str(exe)], env=env, check=True)
        outputs.append(subprocess.check_output([exe]))
        print(label, flush=True)
        subprocess.run([exe, "measure"], check=True)
assert outputs[0] == outputs[1], "formatted bytes differ"
print("The two length-prefixed output streams are byte-identical.")
