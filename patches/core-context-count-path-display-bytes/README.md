# Core: count displayed path bytes without an intermediate string

Context-history summaries use the UTF-8 byte length of Rust's default path display, not the raw platform path length. Both optional `Context` paths and `FileRef` paths now send the same `Path::display()` output to a counting `fmt::Write` sink instead of building a temporary string. Nothing normalizes or opens the path. Unicode replacement, count arithmetic, rounding and saturation, and JSON-size logic are unchanged.

This affects path-bearing parts when Core computes the history summary, including cache publication and checkpoint updates. Text-only histories do not benefit. Existing delivery #284 already supplies the JSON-size helper on this base and must not be reapplied.

## Exact offline check

Use the unpatched Core file from `b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`, the installed Linux x86-64 Rust 1.95.0 compiler, and an existing private scratch directory:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py \
  --stock /path/to/Proteus-core/crates/proteus-core/src/core/session_store/context_summary.rs \
  --rustc /absolute/path/to/rustc \
  --work-dir /path/to/private-scratch
```

The proof verifies both source identities and forward/reverse patch replay, then runs six tests in each of debug and optimized Rust builds. Per build it compares 69,905 exhaustive short paths, 25,000 generated raw byte paths, a 1 MiB mixed path, and 4,096 shaped summary pairs. The summary lift uses precomputed JSON byte lengths, not the real serializer. A scoped allocator witness observed allocations in the stock expression and none inside the new helper for four nonempty path fixtures per build. This is not a Cargo, Windows, cache integration, timing, or application-memory measurement.
