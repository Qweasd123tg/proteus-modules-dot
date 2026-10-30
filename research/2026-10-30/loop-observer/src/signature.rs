//! One bounded exact byte signature, not a hash or retained history.
use std::io::{self, Write};

use proteus_module_sdk::contracts::domain::{ToolCall, ToolResult};
use serde_json::Value;

struct Buffer<'a, F> {
    bytes: Vec<u8>,
    limit: usize,
    cancelled: &'a F,
}

impl<F: Fn() -> bool> Write for Buffer<'_, F> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if (self.cancelled)() {
            // Write::write_all retries Interrupted: use a terminal writer error.
            return Err(io::Error::other("observation canceled"));
        }
        if bytes.len() > self.limit.saturating_sub(self.bytes.len()) {
            return Err(io::Error::other("observation byte limit"));
        }
        self.bytes.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

// Canonicalize only arguments. Sorting references avoids cloning nested Values;
// node/depth limits bound sorting/traversal independently of serialized bytes.
fn argument<W: Write>(
    value: &Value,
    out: &mut W,
    depth: usize,
    nodes: &mut usize,
    key_bytes: &mut usize,
) -> anyhow::Result<()> {
    anyhow::ensure!(depth <= 32, "argument depth limit");
    match value {
        Value::Object(map) => {
            anyhow::ensure!(map.len() <= *nodes, "argument node limit");
            // Reserve all child nodes before allocating sorted references.
            // Nested maps cannot each reserve the same unvisited node budget.
            *nodes -= map.len();
            // Reject an already-impossible byte budget before sorting long keys.
            // Raw UTF-8 key bytes cannot exceed their JSON-encoded byte count.
            for key in map.keys() {
                anyhow::ensure!(key.len() <= *key_bytes, "argument key byte limit");
                *key_bytes -= key.len();
            }
            let mut entries: Vec<_> = map.iter().collect();
            entries.sort_unstable_by(|a, b| a.0.cmp(b.0));
            out.write_all(b"{")?;
            for (index, (key, value)) in entries.into_iter().enumerate() {
                if index != 0 {
                    out.write_all(b",")?;
                }
                serde_json::to_writer(&mut *out, key)?;
                out.write_all(b":")?;
                argument(value, out, depth + 1, nodes, key_bytes)?;
            }
            out.write_all(b"}")?;
        }
        Value::Array(values) => {
            anyhow::ensure!(values.len() <= *nodes, "argument node limit");
            *nodes -= values.len();
            out.write_all(b"[")?;
            for (index, value) in values.iter().enumerate() {
                if index != 0 {
                    out.write_all(b",")?;
                }
                argument(value, out, depth + 1, nodes, key_bytes)?;
            }
            out.write_all(b"]")?;
        }
        _ => serde_json::to_writer(out, value)?,
    }
    Ok(())
}

pub(crate) fn build(
    call: &ToolCall,
    result: &ToolResult,
    limit: usize,
    cancelled: &impl Fn() -> bool,
) -> anyhow::Result<Option<Vec<u8>>> {
    // Preallocate the requested budget. Writes enforce the logical byte cap;
    // allocator capacity/rounding is not an absolute RSS guarantee.
    let mut out = Buffer {
        bytes: Vec::with_capacity(limit),
        limit,
        cancelled,
    };
    let encoded = (|| -> anyhow::Result<()> {
        out.write_all(b"[")?;
        serde_json::to_writer(&mut out, &(&call.name, &call.surface, &call.raw_arguments))?;
        out.write_all(b",")?;
        let mut nodes = 4095; // The root itself is already counted.
        let mut key_bytes = limit;
        argument(&call.args, &mut out, 0, &mut nodes, &mut key_bytes)?;
        out.write_all(b",")?;
        // Exclude only call_id. Rich content, error and metadata all participate.
        // Nested result JSON uses its current serialization order: differing map
        // order may miss a match, but never makes unequal bytes compare equal.
        serde_json::to_writer(
            &mut out,
            &(
                result.ok,
                &result.output,
                &result.content,
                &result.error,
                &result.metadata,
            ),
        )?;
        out.write_all(b"]")?;
        Ok(())
    })();
    anyhow::ensure!(!cancelled(), "loop observer canceled");
    Ok(encoded.ok().map(|()| out.bytes))
}
