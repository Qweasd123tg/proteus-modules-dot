#!/usr/bin/env python3
"""Compare actual stock and patched stream filters without Cargo, network or checkout changes."""
from argparse import ArgumentParser
from pathlib import Path
from shutil import copyfile
from subprocess import check_output, run
from tempfile import TemporaryDirectory

here = Path(__file__).resolve().parent
base = "9469e3b12529d08b1f4a76882693e2065e842c51"
paths = [
    "model/model-pack/src/adapters/anthropic/sanitize.rs",
    "model/model-pack/src/adapters/anthropic/stream/block_tests.rs",
]
parser = ArgumentParser(description=__doc__)
parser.add_argument("repository", type=Path)
parser.add_argument("--mutations", action="store_true", help="verify both guard-removal controls fail")
args = parser.parse_args()

with TemporaryDirectory(prefix="proteus-dsml-") as tmp:
    root = Path(tmp)
    for path in paths:
        dest = root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(check_output(["git", "-C", args.repository.resolve(), "show", f"{base}:{path}"]))
    copyfile(root / paths[0], root / "before.rs")
    # A private repo also handles a TMPDIR nested inside a caller's checkout.
    run(["git", "init", "-q"], cwd=root, check=True)
    run(["git", "apply", "--check", here / "candidate.patch"], cwd=root, check=True)
    run(["git", "apply", here / "candidate.patch"], cwd=root, check=True)
    copyfile(root / paths[0], root / "after.rs")
    copyfile(here / "probe.rs", root / "probe.rs")

    def compile_probe():
        run(["rustc", "--edition=2024", "-O", "-C", "strip=symbols", "probe.rs", "-o", "probe"],
            cwd=root, check=True)

    compile_probe()
    run([root / "probe"], cwd=root, check=True)
    if args.mutations:
        file = root / "after.rs"
        source = file.read_text()
        for label, find, replace in [
            ("ignore pending marker", "self.pending.is_empty() && !text.contains('<')", "!text.contains('<')"),
            ("expose hidden chunk", "return if self.in_tool_block", "return if false"),
        ]:
            assert source.count(find) == 1
            file.write_text(source.replace(find, replace))
            compile_probe()
            result = run([root / "probe"], cwd=root, capture_output=True, text=True)
            assert result.returncode != 0 and "delta #" in result.stderr, result
            print(f"Negative control rejected: {label}.")
