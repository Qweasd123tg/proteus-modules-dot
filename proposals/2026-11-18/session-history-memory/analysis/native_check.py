"""Run rustc on the exact before/after functions from the pinned checkout, plus Python oracle."""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from height_oracle import fixture_bodies, spec

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path, help="Root of Extensions a35cea08be83ee8e5ecbfce9ef5050a1c00eb247")
args = parser.parse_args()
name = Path("packages/analysis/src/nodes.rs")
baseline = (args.source / name).read_bytes()
def blob(contents):
    return hashlib.sha1(b"blob " + str(len(contents)).encode() + b"\0" + contents).hexdigest()
assert blob(baseline) == "9860c5ada746f55ac1bc717d9e2410d3b66856f4"
rustc = os.environ.get("RUSTC", "rustc")
subprocess.run([rustc, "--version"], check=True)
def extract(s):
    start = s.index("/// ", s.index('maybe("selected"')) # after preceding fn, before height helper(s)
    end = s.index("/// A heading that", start)
    return s[start:end]
with tempfile.TemporaryDirectory() as td:
    t = Path(td)
    target = t / name
    target.parent.mkdir(parents=True)
    target.write_bytes(baseline)
    subprocess.run(["git", "apply", "--check", HERE / "analysis-height.patch"], cwd=t, check=True)
    subprocess.run(["git", "apply", HERE / "analysis-height.patch"], cwd=t, check=True)
    after = target.read_bytes()
    assert blob(after) == "762942e98a21d22e7112b98a9c4456309395e6f5"
    before_rs, after_rs = baseline.decode(), after.decode()
    for tag, source in [("before",before_rs),("after",after_rs)]:
        frame = extract(source) + source[source.rindex("#[cfg(test)]"):]
        (t / "tests.rs").write_text(frame)
        subprocess.run([rustc, "--edition=2024", "--test", "tests.rs", "-o", "tests"], cwd=t, check=True)
        print(tag, "extracted upstream height tests:", flush=True)
        subprocess.run([t / "tests"], check=True)
    frame = (HERE / "native.rs.in").read_text().replace("BASELINE",extract(before_rs)).replace("CANDIDATE",extract(after_rs))
    (t / "actual.rs").write_text(frame)
    corpus = t / "cases"
    with corpus.open("wb") as f:
        for body in fixture_bodies():
            b = body.encode()
            f.write(struct.pack("<IHH", len(b), spec(body, False), spec(body, True)));f.write(b)
    for flags in [[], ["--cfg", "count_alloc"]]:
        subprocess.run([rustc, "--edition=2024", "-O", "actual.rs", "-o", "check", *flags], cwd=t, check=True)
        if not flags: subprocess.run([t / "check", "parity", corpus], check=True)
        subprocess.run([t / "check"], check=True)
