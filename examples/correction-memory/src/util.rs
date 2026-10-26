use anyhow::{Result, ensure};
use ring::digest::{SHA256, digest};
use serde::Serialize;
use std::io::{self, Write};
pub fn sha256(bytes: &[u8]) -> String {
    digest(&SHA256, bytes)
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
struct Bounded {
    bytes: Vec<u8>,
    cap: usize,
}
impl Write for Bounded {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        if buf.len() > self.cap.saturating_sub(self.bytes.len()) {
            return Err(io::Error::other("serialized_size_limit"));
        }
        self.bytes.extend_from_slice(buf);
        Ok(buf.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
pub fn canonical<T: Serialize>(v: &T, cap: usize) -> Result<Vec<u8>> {
    let mut w = Bounded { bytes: vec![], cap };
    serde_json::to_writer(&mut w, v)?;
    ensure!(w.bytes.len() <= cap, "serialized_size_limit");
    Ok(w.bytes)
}
