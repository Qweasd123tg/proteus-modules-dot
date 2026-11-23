# Modules rg-search: reuse stdout line scratch

Apply `source.patch` to
`Proteus-harness/Proteus-modules@331cfc20bbaf821ab07de49868426da29ebdeb64`.
Only `context_provider/rg-search/src/lib.rs::read_rg_matches` changes.

The same `BufRead::read_line` calls now share a cleared String. As in
Rust 1.95's `Lines`, an ending LF is removed, followed by one CR only
if one precedes that LF. The reader does not make another call after the
accepted result cap, or read anything at a zero result cap. The original
JSON parser, exact SDK path matcher, stdout/child policy, argv, reader
error order, filter order, and result bounds are unchanged.

Before each read the scratch capacity is at most 8 KiB: a larger buffer
is released before the next call. This is not an input or JSON size
limit. A large line is still read and processed once as before, and can
temporarily use a larger buffer. Short-line allocation churn decreases
at the cost of retaining small scratch capacity across reads.

Pinned Rust 1.95 passed 7/7 tests in debug and optimized builds.
The proof uses the actual reader and parser bodies, the locked SDK
matcher, inert JSON values and ordinary fragmented std BufRead,
including injected I/O failures, interruption and invalid UTF-8.
It compares exact parse inputs, result fields, read consumption and
error order in explicit fixtures and 4,096 generated pairs per mode.
A valid 65 KiB synthetic line was processed before its capacity was
released at the next read.

In either mode, 4,096 identical nonmatch event lines made 4,096 → 1
line-buffer allocations, zero reallocations in either arm, and
69,632 → 17 requested bytes. These are scoped allocator requests
with the fixture scanner, not live rg, Serde, latency, or RSS data.
No process-host or full-Cargo validation was run.

To reproduce, supply the unpatched pinned Modules source and its lock,
the locked Core SDK `crates/proteus-contracts/src/domain/search.rs`,
the Rust 1.95.0 `library/std/src/io/mod.rs`, a pinned Rust compiler and
an existing private scratch directory. The verifier checks exact file
identities, forward replay and rollback. No Git subprocess, Cargo,
ripgrep process, or network is invoked.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --stock "$MODULES/context_provider/rg-search/src/lib.rs" \
  --lock "$MODULES/Cargo.lock" \
  --matcher "$CORE_SDK/crates/proteus-contracts/src/domain/search.rs" \
  --stdio "$RUST_195_SRC/library/std/src/io/mod.rs" \
  --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
