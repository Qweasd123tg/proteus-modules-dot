#!/usr/bin/env python3
"""Run the patched production history-flow tests; no Cargo, GUI, or network."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="patched exact Desktop checkout")
    parser.add_argument("--rustc", default="rustc")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    bundle = Path(__file__).resolve().parents[1]
    provenance = json.loads((bundle / "provenance.json").read_text())
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=upstream, text=True
    ).strip()
    if actual != provenance["upstream_commit"]:
        raise SystemExit(f"Wrong base: {actual}; expected {provenance['upstream_commit']}")
    for source in provenance["source_files"]:
        path = upstream / source["path"]
        if not path.is_file() or blob_sha(path.read_bytes()) != source["patched"]:
            raise SystemExit(f"Patched source mismatch: {source['path']}")

    source = upstream / "src/ui/chat/history_flow.rs"
    with tempfile.TemporaryDirectory(prefix="proteus-history-flow-") as directory:
        work = Path(directory)
        driver = work / "driver.rs"
        driver.write_text(
            f"#[path = {json.dumps(str(source), ensure_ascii=False)}]\nmod history_flow;\n"
        )
        binary = work / "history-flow-tests"
        subprocess.run(
            [args.rustc, "--edition=2024", "--crate-name", "proteus_history_flow_tests",
             "--test", str(driver), "-o", str(binary)],
            check=True,
        )
        subprocess.run([str(binary), "--nocapture"], check=True)


if __name__ == "__main__":
    main()
