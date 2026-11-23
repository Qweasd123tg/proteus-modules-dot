# Core context-map telemetry: count distinct logs once per eviction

Apply `source.patch` to the exact Core V4 source
`Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`.
Only `crates/proteus-core/src/app_server/context_map/telemetry/cache.rs` changes.

The cache still drops old rows in order to meet its 128-entry and 8 MiB
limits. From those remaining, one reverse scan finds the longest suffix
with at most 16 distinct log paths. The same borrowed PathBuf order is
used. A seventeenth distinct path and the older prefix are then dropped
in exactly the previous order, with the same per-row debit and lock
scope. Size admission, source stamps, duplicate replacement, hit
reordering, and stale-entry removal are unchanged. No configuration,
event parsing, or source identity rules change.

Exact pinned Rust 1.95 debug and optimized builds passed seven paired
tests each, including 186,600 generated cases each against an
independent suffix oracle. The complete paired cache files use inert
telemetry/serialization/stamps with the original Mutex, Budget and
get/insert logic. Cases cover entry/byte admission, serializer failure,
duplicate replacement, stamp and alias hits, shared and non-UTF-8 paths,
wrapped deque storage, and locked oldest-first destruction. A separate
copy of the same eviction blocks counts path visits and set builds.

On one 128-entry, 17-log fixture, both kept the same 16 rows and
131,192 bytes and dropped the same 112 oldest rows. The stock eviction
built 113 sets and visited 8,136 paths. The reverse scan built one set
and visited 17 paths. This is a multi-log eviction-pressure result, not
a cache-hit, ordinary single-log insertion, latency, or RSS result.
No live app endpoints, real Serde/metadata, or Cargo workspace were run.

To reproduce, provide the **unpatched** pinned source and Rust 1.95
compiler and an existing private scratch directory. The proof verifies
both source hashes and exact forward and reverse patch application before
compiling. No Git subprocess or network is used in the proof.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py \
  --stock "$CORE/crates/proteus-core/src/app_server/context_map/telemetry/cache.rs" \
  --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
