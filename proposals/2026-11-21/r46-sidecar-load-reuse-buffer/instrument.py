#!/usr/bin/env python3
"""Inject test-only loader variants and a scoped synthetic probe into a disposable checkout."""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
a = p.parse_args()
src = a.checkout / "storage/session-storage/src/service/catalog/durable.rs"
s = src.read_text()
start = s.index("pub(super) fn load(")
end = s.index("fn journal_kind(", start)
load = s[start:end]
after = "        || index.summary.descriptor.session != descriptor.session"
header = load[:load.index("    let mut bytes")]
tail = load[load.index(after):]
reuse_hash = '''r46_checksum(|| {
        bytes.clear();
        serde_json::to_writer(&mut bytes, &index).ok()?;
        Some(crate::io::sha256_hex(&bytes))
    })?'''
parse = '''    let {mut}bytes = crate::io::bounded_read(&dir.join(FILE), MAX_BYTES).ok()?;
    let Envelope {{
        checksum,
        data: index,
    }} = serde_json::from_slice(&bytes).ok()?;
'''
common = '''r46_checksum(|| {
        Some(crate::io::sha256_hex(&serde_json::to_vec(&index).ok()?))
    })?'''
stream = '''r46_checksum(|| {
        let mut writer = R46Digest(ring::digest::Context::new(&ring::digest::SHA256));
        serde_json::to_writer(&mut writer, &index).ok()?;
        Some(crate::io::digest_hex(writer.0.finish()))
    })?'''
buffer = '''r46_checksum(|| {
        let mut digest = R46Digest(ring::digest::Context::new(&ring::digest::SHA256));
        let mut writer = std::io::BufWriter::with_capacity(8 * 1024, &mut digest);
        serde_json::to_writer(&mut writer, &index).ok()?;
        writer.flush().ok()?;
        drop(writer);
        Some(crate::io::digest_hex(digest.0.finish()))
    })?'''
variants = [
    ("stock", parse.format(mut=""), common, False),
    ("early_drop", parse.format(mut="") + "    drop(bytes);\n", common, False),
    ("reuse", parse.format(mut="mut "), reuse_hash, True),
    ("stream", parse.format(mut="") + "    drop(bytes);\n", stream, False),
    ("buffered", parse.format(mut="") + "    drop(bytes);\n", buffer, False),
]
out = ["#[cfg(test)]\nmod r46_load_probe {\nuse super::*;\n"]
for name, body, expr, drop_after in variants:
    prefix = header.replace("pub(super) fn load(", f"fn {name}(") + body
    suffix = "    drop(bytes);\n" if drop_after else ""
    out.append(prefix + f"    let digest = {expr};\n" + suffix + "    if checksum != digest\n" + tail)
out.append((Path(__file__).parent / "load_probe.rs").read_text())
out.append("}\n")
src.write_text(s + "\n" + "".join(out))
