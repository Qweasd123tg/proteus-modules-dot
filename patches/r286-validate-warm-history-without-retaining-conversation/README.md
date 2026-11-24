# Verify a fresh detached transcript cache hit without retaining unrelated typed rows

The unattached full-history HTTP reader used to build a complete cached SessionReadModel, even though it returns only the rendered transcript. On a fresh persisted cache hit, the patch still reads and validates all cached canonical messages and model-context observations, but drops the owned rows as they are visited. It never constructs an incomplete/fake model or retains an aggregate canonical/context output buffer for this caller.

Original full-model callers still collect the same complete canonical and context vectors. Both loaders share one HEAD/source pipeline, the exact existing model/actual-row-count/usage/workspace predicate, and the same final source recheck. Leaf validation, packed-frame limits and decode, content hashing, narrower row types, actual per-leaf row count, transcript allocation/capacity, source identity or freshness semantics, and operation ordering are preserved. Failed cache verification invokes the unchanged projected/strict whole-model fallback. Only the detached branch of the full transcript endpoint switches helpers; the active branch source, named and paged callers, and conversation/context endpoints are not changed.

The production patch changes four files against Core `b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`: cache.rs `4e22c9457706af44e7bb52bbe8ff9b680c8dc19b`, view.rs `f812aa6b399ce191b3eb9981057630507749072a`, app_server/read_model.rs `f8cd2c980b39a838970013d2754a5b4e01c189c8`, and app_server/http/sessions.rs `3259d16a154b96981435013a5d600302278f7243`. The new helper is placed after the unchanged existing full reader so this patch and #587 apply in either strict order.

## Measurement scope

The Linux x86-64 release harness exercises the exact detached closure and typed source reader backed by the genuine cache writer, original snapshots/renderer and pinned contracts/session-semantics, using a typed fixture at the worker storage boundary. Only the first persisted fresh hit is measured, not cold seed/render or cache population. The source bind and both opened snapshot releases are checked; an accepted warm result must not write cache or render anything. An unrelated runtime/active HTTP server was not executed.

The current-thread ledger tracks exact requested Layouts and allocation generation at each true accepted typed leaf, tagging leaf slots, actual nested message/row owners, and full vector aggregates separately. A reused address cannot stand for an earlier generation. Captures are before the first rendered transcript section read and before final fingerprint. A second result, canonical typed-owner high-water, is sampled at actual decoded leaf and aggregate boundaries. Untyped JSON value trees, packed payloads/inflate scratch, allocator spare pages, recording overhead, storage caches, native worker-process RAM, RSS/PSS, total CPU/time and Desktop launch are not included. The same cached leaves may still be decoded and allocated on both arms.

## First observed outcomes

Both locked Serde builds passed 136 paired route checks, including 26 verified warm full-history cases and 14 warm cases with nonempty model context per layout. The large projected and strict cache origins agreed. For the public four-repeat Cyrillic text shape:

| Fresh persisted cache hit | Retained stock before transcript and final recheck, default | Retained stock, preserve_order | Retained original canonical/context owners in candidate |
|---|---:|---:|---:|
| 5,000 messages | 3,403,890 B / 10,001 allocations | 3,803,890 B / 10,001 allocations | 0 |
| 50,000 messages | 34,088,890 B / 100,001 allocations | 38,088,890 B / 100,001 allocations | 0 |

The candidate does not stop decoding these rows. Both arms accepted 100 or 1,000 canonical leaves at the two sizes, each at most 50 rows, and checked the same fingerprints and releases. The original canonical aggregate vector requested 6,400,000 B at 50k in default and 8,400,000 B in preserve_order; this vector is not created by the new loader. Both arms still retain the same rendered payload through the final fingerprint, e.g. 46,013,890 B in default at 50k, with unchanged original rendered capacities and complete output bytes.

For canonical typed-owner high-water at the explicit decoded leaf/aggregate boundaries, 50k was 34,095,290 → 34,100 B in default and 38,097,290 → 38,100 B in preserve_order. This measures typed owners only, not decode scratch, storage, overall process peak, cold launch, or time. Full-model controls still hold and return their complete canonical and model-context vectors. Multi-leaf context controls use the genuine writer with deliberately supplied synthetic valid context observations; the small nonempty fixture also exercises a context observation produced by actual history compaction projection.

Fault controls include valid-content-addressed but invalidly typed or wrong-cardinality leaves in all three sections, first and late, with exact checksum/pack/head references recomputed. The test checks that those objects reach the typed decode/cardinality guard (not just a cheap hash rejection), suppresses the final warm recheck when a leaf was rejected and expects cold fallback instead. Separate cases cover bad physical hashes, missing or malformed storage responses, invalid declared bytes, packed inflate failures, HEAD/source drift or false identity, checked release faults, and real projected/strict fallback/write/error precedence. Invalid durable journal after a late type failure remains an error. Named and paged reads are independent controls, not targets of this allocation claim.

`GATES.md`, both first raw JSONL files and their summaries contain the gate results. `check_layout.py` checks owner generations and route results; `check_route.py` separately checks physical packs, request paths, decode attempts and warm/cold behavior. See `route-scope.md` for exact scope. The portable proof verifies the pinned source, registry archives and feature graphs and can replay offline with `python3 proof.py --core CORE --archives ARCHIVES --rust-bin RUST_BIN --work NEW_EMPTY_DIR --action run`. The supplied portable proof was staged; actual executions used the pinned offline build lane. No external writes or deployment.

## Raw receipt transport

The complete first-run receipts are stored as Base64-wrapped gzip. Decode them before running the receipt checkers directly:

```sh
for mode in default preserve_order; do
  base64 -d "$mode.jsonl.gz.b64" | gzip -dc > "$mode.jsonl"
done
sha256sum -c RAW-SHA256SUMS
```
