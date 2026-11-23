# End cold cache model ownership before the named page read

Target: [Proteus Core at b2d2e6de](https://github.com/Proteus-harness/Proteus-core/tree/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14). The patch changes only `crates/proteus-core/src/core/session_store/remote/view.rs`.

After the model save returns, keep its scalar revision. In the existing paged path, drop its owned canonical conversation and prefix identities before looking up the named revision. Keep the full rendered transcript alive until a verified named page is returned. A failed save does not skip the separate lookup. A failed or unavailable lookup still returns the whole rendered transcript with no cursor. Validation, save order, source revision, lookup arguments, response and unpaged lifetimes are unchanged. The warm provisional-cache path does not use this code.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

## Observed at the named-reader entry

The stock and candidate proofs each constructed 50,000 real typed canonical messages with the public fixture's four-repeat text pattern, independent rendered display rows, and an exact typed journal record for the prefix scan. The save adapter armed the allocator tracker as it exited. Before the named-reader adapter made any allocations for its response, the stock retained all watched owners; the candidate had already freed:

| Owner | Allocations already freed | Requested bytes, default map | Requested bytes, preserve order |
|---|---:|---:|---:|
| Canonical row vector | 1 | 8,388,608 | 11,010,048 |
| Canonical per-message part vectors | 50,000 | 32,000,000 | 40,000,000 |
| Canonical text buffers | 50,000 | 19,688,890 | 19,688,890 |
| Current-history fingerprint vector | 1 | 2,097,152 | 2,097,152 |
| Prefix identity hash tables | 3 | 3,342,384 | 3,342,384 |
| **Total** | **100,005** | **65,517,034** | **76,138,474** |

The owning DTO layout changes with the dependency’s map representation; within each feature graph the output and counts agree across debug and optimized builds. Both arms kept the full fallback transcript alive at the reader entry. After the operation, both had freed the same original allocations, except the fallback transcript when returned. The tracker records each watched original allocation's first matching deallocation interval and ignores later address reuse. Hash-table bytes come from the deallocator's layout, not from a capacity estimate. The mixed-size control also verifies freeing a nonempty model-context vector.

These are requested sizes of watched allocations whose destruction moved earlier in this fixture, not allocation traffic avoided, allocator resident bytes, or a reduction in process peak. The canonical model and transcript are still live together through the previous rendering and cache-save phases. The existing Linux/glibc trim runs after the view returns in either arm. No upstream app, user session, native first-open latency, RSS/PSS or whole-run peak was measured.

## Scope and reproduction

The proof compares 13 scenarios in stock and candidate, Rust 1.95.0 debug and release, under real serde_json 1.0.151 default and preserve-order feature graphs. The cases cover cold 50k, ordinary/empty pages, failed HEAD after a named write, early save error with and without an existing named page, missing/corrupt named header or body, unpaged bypass, and injected render/scan/summary errors. It verifies independent ordered adapter traces, the exact serialized output/cursor, the existing full fallback Vec allocation, and lifetime at the named-reader boundary.

The isolated proof lifts the exact production projection and `from_validated`, `display_prefix`, prefix membership and revision/hash functions and both public-to-cache wrappers. It uses actual pinned Serde, UUID and Ring and exact exercised DTO declarations. The shortened JournalEntry excludes four unrelated hook/request/context variants. A test-only receiver wrapper retains each projection function verbatim, and test-only allocation observation reads the otherwise private set members. Snapshot cursor/state, rendering, cache backend/storage I/O and injected faults are adapters. The proof does not execute the real cache writer, worker, external read protocol or renderer. It leaves native cache integration and phase sampling for follow-up.

From an exact Core checkout and a clean work directory, use the official archives listed in the embedded proof lock and the matching Rust/Cargo/rustfmt distribution. You can pass multiple archive directories:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --source /path/to/exact/Core --work /path/to/scratch \
  --toolchain-bin /path/to/rust-1.95.0/bin --archives /path/to/official-archives
```

The verifier checks source Git blob and SHA-256 pins, exact forward/reverse application, formatting, official Core lock checksums, offline builds, and stable output/liveness receipts. The packet does not change upstream or install anything.
