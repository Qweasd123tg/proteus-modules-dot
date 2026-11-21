"""Exercise actual baseline and patched receipt handling with locked Core dependencies."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SRC = Path("crates/proteus-core/src/core/agent_control/process/messaging.rs")
TESTS = Path("crates/proteus-contracts/tests")
PATCH = HERE / "source.patch"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
p.add_argument("target", type=Path)
args = p.parse_args()

# Both copies are compiled together; preparation and result serialization are
# outside the allocator scope. The stub ChildProcess's send is uncallable.
def setup(probe, prod, filename, output_arg):
    body = prod.read_text()
    body += '''
#[path = "measure.rs"]
pub(crate) mod proof_cases;

fn call_confirm(
    tracker: &mut PeerMessageDelivery,
    id: &str,
    ok: bool,
    output: &mut Option<Value>,
    error: Option<&str>,
) -> Result<Option<PeerMessageResponse>> {
'''
    body += f"    tracker.confirm(id, ok, {output_arg}, error)\n}}\n"
    (probe / filename).write_text(body)

env = dict(os.environ, CARGO_TARGET_DIR=str(args.target.resolve()))
for k, v in {"CARGO_BUILD_JOBS": "1", "CARGO_PROFILE_TEST_DEBUG": "0",
             "CARGO_INCREMENTAL": "0", "RUST_TEST_THREADS": "1"}.items():
    env.setdefault(k, v)
with tempfile.TemporaryDirectory(prefix="proteus-r52-receipts-") as temp:
    root = Path(temp)
    tree = root / "core"
    shutil.copytree(args.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    subprocess.run(["git", "apply", "--check", PATCH], cwd=tree, check=True)
    dest = tree / TESTS
    cases = dest / "r52_peer_cases"
    cases.mkdir()
    shutil.copyfile(HERE / "harness.rs", dest / "r52_peer_receipts.rs")
    shutil.copyfile(HERE / "measure.rs", cases / "measure.rs")
    setup(cases, tree / SRC, "base.rs", "output.as_ref()")
    subprocess.run(["git", "apply", PATCH], cwd=tree, check=True)
    setup(cases, tree / SRC, "candidate.rs", "output")
    snap = root / "outputs.json"
    cmd = ["cargo", "test", "--locked", "--offline", "-p", "proteus-contracts",
           "--test", "r52_peer_receipts", "--", "--nocapture"]
    result = subprocess.run(cmd, cwd=tree, env={**env, "R52_RECEIPT_SNAPSHOT": str(snap)},
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout)
    for line in result.stdout.splitlines():
        if "r52 " in line:
            print(line[line.index("r52 "):])
        elif line.startswith("test result:"):
            print(line)
    data = snap.read_bytes()
    print(f"16 serialized snapshots ({len(data)} bytes) pairwise equal; SHA256 {hashlib.sha256(data).hexdigest()}")
