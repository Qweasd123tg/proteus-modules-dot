# Core: read Git log fields one record at a time

The workspace Git log decoder now groups the existing NUL-split fields eight at a time instead of collecting every field reference in a vector. It still uses `str::split`, including its last field when empty or unterminated. Short groups are ignored. One group beyond the requested page sets `has_more` before timestamp parsing, exactly as before.

This changes only decoder scratch. Git arguments, the output cap, lossy UTF-8 conversion, ordering, decorations, and response fields are unchanged. In the synthetic 501-record terminated fixture, the old vector stores 4,009 field references, or 64,144 bytes of reference payload on Linux x86-64. The new iterator produces one 128-byte array of eight field references at a time, plus constant iterator state. This is a structural comparison, not measured allocator use, total stack usage, time, or process memory.

## Exact offline check

Use the unpatched file from `Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14` and the installed Linux x86-64 Rust 1.95.0 compiler. The exact base already includes delivery #280.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py \
  --stock /path/to/Proteus-core/crates/proteus-core/src/app_server/http/workspace/git/log.rs \
  --rustc /absolute/path/to/rustc \
  --work-dir /path/to/private-scratch
```

The proof checks forward and reverse patch replay, then compiles both decoder tails and decoration functions against synthetic byte buffers, an inert input/limit adapter, and the original row field shapes. Seven tests pass in each of debug and optimized builds, including 29,524 generated field-group pairs, 3,000 mixed cutoff/limit/flag checks, terminal empty fields, incomplete tails, timestamp error priority, and 50/500-row page boundaries. No Git, HTTP, serde, or full Core package ran.
