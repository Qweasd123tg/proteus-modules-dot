# Core: hash small plain history rows in one digest call

After the stored transcript is rendered, `display_prefix` in
`crates/proteus-core/src/core/session_store/remote/view.rs` computes the
journal digest of every canonical history message. A singleton text part
without metadata, name or call binding can use one 1-KiB stack buffer to
encode the canonical row before SHA-256. Only texts of at most 85 UTF-8 bytes
are admitted; even all JSON control characters can fit in the reserved text
budget. It is still Serde's canonical message encoder. Unknown/long/mixed
rows use the prior streaming writer unchanged; if a future schema unexpectedly
overfills the stack buffer, the partial encoding is discarded. No cache
format, validation, errors, or serialized contract changes.

**Native differential.** Exact M350 before source and patched after source,
the same frozen M350 Contracts types, Ring, Serde and Rust 1.95. Pinned
single-thread Linux release, 16 alternating-order A/B pairs per shape and mode.
Each row was also compared to SHA-256 of independent `serde_json::to_vec`;
the 1,038 additional cases per mode include a non-UTF-8 path error, escape
bytes, UTF-8, nested metadata and large and boundary inputs. Each mode passed
all 19 actual Session Semantics crate unit tests. Source patch passes strict
forward and inverse Git checks. The two feature modes are default maps and
explicit `serde_json/preserve_order`.

Plain 50k rows used ~20% less paired median hash CPU in both modes. Mixed
50k used ~9–10% less. 25k maximum eligible 85-byte rows used ~18–20% less;
the 86-byte, 512-byte, escape-heavy 512-byte, and 1-MiB bypass arms were all
within 2% of the prior paired median. All raw per-arm samples and checksums
are attached. See receipt.json for exact scoped numbers. No desktop startup,
latency-to-first-visible-line, peak/steady memory or PSS improvement is
established by this read-path microbenchmark.

No all-row optimization was selected. Prototype buffered writers sped up short
text but regressed 1-MiB flat strings, while admitting medium rows after a
character scan could regress 512-byte text. Neither prototype is in the patch.

**Portable replay.** From a disposable root, put exact frozen M350 Core (archive
SHA in receipt) under `src/`. Create `hash/proof/` and `hash/baseline/`.
Copy the original `src/crates/proteus-session-semantics/src/journal/message_hash.rs`
to `hash/baseline/message_hash.rs`. Apply source.patch at `src/`. Put
native-proof.rs, proof-Cargo.toml and proof-Cargo.lock in `hash/proof/` under
the names main.rs, Cargo.toml and Cargo.lock. With the exact locked registry
available, run `cargo run --release --locked` and `cargo run --release
--locked --features preserve_order` inside that directory. Pin a free CPU
on Linux (the harness records CLOCK_THREAD_CPUTIME_ID as well as wall time).
