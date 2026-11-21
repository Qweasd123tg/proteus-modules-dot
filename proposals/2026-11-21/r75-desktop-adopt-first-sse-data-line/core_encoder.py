"""Materialize exactly the verified Core encoder from the pinned archive."""
from hashlib import sha256
from pathlib import Path
import sys, tarfile, tomllib

archive, out = map(Path, sys.argv[1:])
PIN = "32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f"
SHA = "88daf295821553f47122d274182fcc6332abd23441802882ba57e6b07a4d2dd2"
member = f"Proteus-core-{PIN}/crates/proteus-core/src/app_server/http/sse.rs"
with tarfile.open(archive, "r:gz") as src:
    raw = src.extractfile(member).read()
    lock = tomllib.loads(src.extractfile(f"Proteus-core-{PIN}/Cargo.lock").read().decode())
    bytes_rows = [p for p in lock["package"] if p["name"] == "bytes"]
    assert len(bytes_rows) == 1
    assert bytes_rows[0]["version"] == "1.11.1"
    assert bytes_rows[0]["checksum"] == "1e748733b7cbc798e1434b6ac524f0c1ff2ab456fe201501e6497c8417a4fc33"
anchor = b"pub(super) fn encode_sse_output("
assert raw.count(anchor) == 1
exact = raw[raw.index(anchor):]
assert sha256(exact).hexdigest() == SHA
out.write_bytes(b"use bytes::Bytes;\nuse proteus_contracts::app_protocol::StdioOutput;\n\n" + exact)
print(f"PASS exact Core pin {PIN} encoder {SHA} and its locked bytes 1.11.1")
