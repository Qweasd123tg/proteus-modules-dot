"""Compare unchanged production renderers with a deterministic fixed-prefix scanner.

The standalone build omits unexercised append entry points. It counts net live
requested Rust heap bytes across scan #1, not IPC/PSS or JSON parsing cost.
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from build import compile_stand, git

parser = argparse.ArgumentParser()
parser.add_argument("repository", type=Path)
parser.add_argument("stock")
parser.add_argument("candidate")
parser.add_argument("deps", type=Path)
parser.add_argument("rustc", type=Path)
parser.add_argument("--rows", type=int, default=125000)
parser.add_argument("--pairs", type=int, default=5)
a = parser.parse_args()

prefix = "crates/proteus-core/src/app_server/"
files = [
    "transcript.rs", "transcript/rows.rs", "transcript/journal.rs",
    "transcript/journal/source.rs", "transcript/journal/timestamps.rs",
]
with tempfile.TemporaryDirectory() as tmp:
    variants = {}
    for variant, ref in [("stock", a.stock), ("candidate", a.candidate)]:
        directory = Path(tmp) / variant
        directory.mkdir()
        for filename in files:
            source = git(a.repository, "show", f"{ref}:{prefix}{filename}")
            if filename == "transcript.rs":
                source = source.replace(
                    "    journal_transcript_append_committed, journal_transcript_append_from_source,\n", ""
                )
            elif filename == "transcript/journal.rs":
                first = source.index("mod append;")
                after = source.index("mod timestamps;", first)
                source = source[:first] + source[after:]
            path = directory / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        shutil.copy(Path(__file__).with_name("stand.rs"), directory / "stand.rs")
        variants[variant] = compile_stand(
            a.rustc, a.deps.resolve(), directory, ["anyhow", "proteus_contracts", "serde_json"]
        )
    for pair in range(a.pairs):
        names = ["stock", "candidate"] if pair % 2 == 0 else ["candidate", "stock"]
        for variant in names:
            report = subprocess.check_output([variants[variant], str(a.rows)], text=True)
            print(pair + 1, variant, report.strip(), flush=True)
