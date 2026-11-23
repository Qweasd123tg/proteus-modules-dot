# Core: bound scratch space for untracked-file line counts

The `/workspace/changes` path used to collect up to 512 KiB from each admitted untracked file into a heap vector, then scan the bytes for NUL and LF. The patch counts LF bytes and tracks the last byte with one fixed 8 KiB stack buffer. A NUL still produces no line count. The reader drains input to EOF or the existing byte cap after detecting NUL, retries interruptions, and rejects other read errors.

The path join, symlink metadata check, regular-file check, 512 KiB per-file cap, 4 MiB shared budget, metadata-size debit before open, capped reads, and tracked-file Git stats are unchanged. This is not a stronger filesystem snapshot or a change to the existing path policy. Different read request sizes can affect syscall count and interactions with files modified in flight.

## Exact offline check

The patch targets `Proteus-harness/Proteus-core` at commit `b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`. Use the unpatched `stats.rs` at that commit, installed Rust 1.95.0, and an existing private scratch directory on Linux:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py \
  --stock /path/to/Proteus-core/crates/proteus-core/src/app_server/http/workspace/git/stats.rs \
  --rustc /absolute/path/to/rustc \
  --work-dir /path/to/private-scratch
```

The proof validates both source hashes and the patch, checks forward and reverse replay, and compiles the unchanged stock file-count function and the candidate function/helper as extracted from the exact sources. Fault injection uses the stock code after file open with only the reader replaced. Seven Rust tests passed: 30 paired real-file decisions, 58,593 paired fragmented short streams, and 10 paired EOF/error/interruption/cap scripts. The test runs no Git command, HTTP endpoint, or Cargo build. It does not measure latency, CPU, RSS, or syscall count.
