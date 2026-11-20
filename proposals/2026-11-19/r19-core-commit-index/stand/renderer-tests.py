"""Run the actual in-memory transcript modules and their tests, not Core / storage integration."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from build import compile_stand, git

parser = argparse.ArgumentParser()
parser.add_argument("repository", type=Path)
parser.add_argument("ref")
parser.add_argument("deps", type=Path)
parser.add_argument("rustc", type=Path)
a = parser.parse_args()
prefix = "crates/proteus-core/src/"

with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    paths = git(
        a.repository, "ls-tree", "-r", "--name-only", a.ref, "--",
        prefix + "app_server/transcript", prefix + "app_server/transcript.rs",
        prefix + "core/session_store/remote/view/prefix.rs",
    ).splitlines()
    for key in paths:
        source = git(a.repository, "show", f"{a.ref}:{key}")
        name = key.removeprefix(prefix)
        if name.endswith("/prefix.rs"):
            # Omit the unused cache codec; the in-memory prefix visit stays intact.
            name = "core/prefix.rs"
            source = source.replace("mod packed;", "")
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    shutil.copy(Path(__file__).with_name("renderer-tests.rs"), directory / "stand.rs")
    binary = compile_stand(
        a.rustc, a.deps.resolve(), directory,
        ["anyhow", "proteus_contracts", "serde_json", "serde", "proteus_session_semantics"],
        test=True,
    )
    subprocess.run([binary, "--test-threads=1"], check=True)
