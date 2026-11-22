"""Exact Desktop framing/parser split plus a test-only payload-copy counter."""
from pathlib import Path
from sys import argv

source, output = map(Path, argv[1:])
raw = source.read_text()
start = raw.index("pub struct EventStream {")
end = raw.index("\n#[cfg(test)]\nmod connection_identity_tests", start)
source = raw[start:end]
marker = "data.push_str("
assert source.count(marker) in (1, 2)
source = source.replace(marker, "crate::ledger::append(&mut data, ")
checkpoint = "            let "
start = source.index(checkpoint + ("trimmed" if "let trimmed = line.trim_end_matches" in source else "line") + " = line.trim_end_matches")
source = source[:start] + "            crate::ledger::sample_capacity(&data, &line);\n" + source[start:]
(output / "stream.rs").write_text(
    "use std::io::{BufRead, BufReader};\n"
    "use anyhow::{Result, anyhow};\n"
    "use proteus_contracts::app_protocol::{AppServerEvent, StdioOutput};\n\n"
    + source
    + """
pub fn for_fixture(capacity: usize, reader: impl std::io::Read + Send + 'static) -> EventStream {
    EventStream { reader: BufReader::with_capacity(capacity, Box::new(reader)) }
}
"""
)
