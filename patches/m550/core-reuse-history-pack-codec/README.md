# Core: reuse independent historical-page encoding scratch

Exact baseline: Core M380, 1,100 complete tracked source files checked
against the independently composed archive (M376 plus #619). The patch
changes only the cache page writer and private historical pack codec. No
new dependency, worker behavior, authority, source check, byte limit,
publication rules, reader, format version, or durable journal changes.

Each accepted historical leaf previously allocated a new raw serialization
buffer, a miniz compressor with separate owned scratch buffers, and a
compressed output Vec. Each invocation of write_pages now owns one lazy codec
workspace. serde_json still serializes the same built Value, the exact
typed-row size comparison still decides whether the original leaf bypasses
packing, and raw level-1 deflate starts with an empty dictionary at each leaf.
miniz's public reset API reuses scratch rather than carrying compression state.
The return Base64 String remains independently owned. Singletons/oversized
leaves, request ordering, guards, pack and page hashes, source-bound header
and the named-page miss fallback remain intact.

No compression allocation for an all-tail or all-oversized section. A
size-mismatch does not keep its enlarged raw buffer. First nonhistorical
page releases scratch; so does the end of write_pages before the final pack
flush. While still packing history, scratch can outlive a leaf and coexist
with a pack flush (including an oversized historical singleton). This
trades bounded retained temporary capacity for much less allocation churn;
it is not a reduction in live heap, whole-app startup latency, RSS or PSS.

## Evidence and reproducibility

* Full M380 input inventory comparison, exact two-leaf forward replay and
  restoration. source-replay.json lists all pre- and post-image hashes.
* Two codec-specific compiled tests per serde layout (default/ordered) cover
  alternating deterministic high-/low-entropy streams, empty input, 32/64
  KiB boundaries, near pack cap, multiple deflate blocks, Unicode/escapes,
  and serialized-size mismatch followed by another exact leaf. Both layouts
  also ran three unchanged source-lift unit tests.
* Exact Core startup/cache/renderer read path over typed in-process storage
  adapter: 58 general projected/strict/unsupported, page/cache/HEAD/named
  faults and fallback controls, seven page pack matrix controls (empty,
  tail-only, singleton, multi-leaf, high entropy, oversize, 4 MiB row split),
  and two 50,000-row startup fixtures per serde layout. Request order, page
  keys and exact payloads, manifest/header bytes, error/fallback, visible
  page and outgoing cache writes were unchanged.
* The allocator scope spans eligible leaf serialization through compressed
  output and Base64 result. It counts requested System alloc/realloc bytes
  gross over a complete run, explicitly excluding the observer's own live
  allocation map. These are cumulative request bytes, not retained bytes.
  Counters, case evidence, dependency checksums and lift scripts accompany the
  patch. Exact locked Rust 1.95.0 and miniz 0.8.9.

| 50,000-row fixture | serde layout | gross codec requests before → after |
| --- | --- | ---: |
| Projected, ×4 text | default | 600,650,262 → 3,548,286 bytes |
| Strict fallback, ×5 text | default | 614,927,994 → 3,801,218 bytes |
| Projected, ×4 text | ordered | 600,770,246 → 3,668,270 bytes |
| Strict fallback, ×5 text | ordered | 615,103,382 → 3,976,606 bytes |


Each fixture encoded 1,998 matching eligible leaves across canonical and
display sections. A section containing only one eligible historical leaf
cannot amortize the boxed compressor: it adds one heap allocation (~64 KiB
gross in the singleton case; its LZ table was previously on the stack).
Tail-only and oversized-only still make zero codec heap requests.

An earlier prototype switching miniz to a callback output destination was
rejected because an additional deterministic high-entropy corpus produced
different exact Base64 bytes. The final patch deliberately preserves the
locked miniz compress_to_vec slice length/growth schedule (not the
callback), and the timing corpus is also an independent bitstream gate:
SHA-256 of all 1,000 complete encoded leaves must match for each layout
and each of display-shaped, canonical-shaped and high-entropy corpora.
The rejected variant and evidence remain labeled HOLD in the archive.

The Rust native test and A/B route harness use exact production selections,
native M380 Semantics and locked external dependencies on a typed
in-process boundary. A separate CPU-affinity timing probe uses the exact
codec blocks and pre-built 50-row JSON leaves; one untimed warmup and seven
samples per process in ABBA order, two processes/arm per shape/layout.
Each timed sample serializes, compresses and Base64-encodes 1,000 leaves,
including scratch cleanup. It excludes page formation/hash/storage, all
worker I/O, application startup and renderer time. Timing is evidence of
the codec only, not a forecast of user-visible startup.

| Scoped codec corpus | Layout | Median before → after | Change |
| --- | --- | ---: | ---: |
| display | default | 89.84 → 56.63 ms | -37.0% |
| strict | default | 149.40 → 103.89 ms | -30.5% |
| entropy | default | 524.91 → 491.82 ms | -6.3% |
| display | ordered | 94.03 → 55.02 ms | -41.5% |
| strict | ordered | 127.86 → 92.26 ms | -27.8% |
| entropy | ordered | 489.89 → 473.02 ms | -3.4% |

Native proof archive retained separately; SHA-256: `99e052ad05f27daa7892538424c3ff8950c521d9ceb7897d3ea9479517ca7561`.
