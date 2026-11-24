# Modules: validate a cold snapshot without building unused projections

The cold branch of `OpenSnapshot` validates the whole committed journal before it returns a fixed source identity. The existing fold also builds usage and model-context objects that the identity and catalog do not use. This patch keeps the strict validator and stops building those two unused projections in that branch. The same branch can run on the first `WriteCache` when it verifies the source and no usable prefix hint is available.

Only `source.patch` changes production code. The target is [Proteus-modules 331cfc20](https://github.com/Proteus-harness/Proteus-modules/tree/331cfc20bbaf821ab07de49868426da29ebdeb64), `storage/session-storage/src/service/views.rs` and `storage/session-storage/src/snapshot.rs`. Sequence overflow, schema/session/sequence checks, strict history/attribution/lifecycle validation, decoding and blob budgets, capture of prior file boundaries, source-version/fingerprint rechecks, catalog bytes/publication and reset order remain in the same places. Full folds, usage-only folds, writer state, warm hint paths, `OpenDisplaySnapshot`, and downstream reads still do the work they use. No wire/storage-format or configuration change.

## Native evidence

Both arms build the full original `session-storage` crate with the exact two Core dependencies pinned by Modules (contracts and journal semantics at `0c1b7572`). They exercise the actual `StorageService::execute` dispatch, both physical JSONL and SQLite backends, byte encoding, strict validation and read/write routes. This is not a build of the full Modules workspace, the standalone storage worker/IPC, or Desktop.

- The new cold reader scans a genuine 33-record journal. For both backends, an ordinary warm reopen then decodes and hashes zero rows/bytes. The native queries get the same canonical history, usage tokens and context (including the distinct before-turn cut), and the unmodified display route still returns the full state. A first cold cache write rejects a stale hash without writing a cache object but can publish the valid catalog, and a current hash writes exactly the admitted value and ETag.
- A carried live reader checks zero, remembered and unremembered cuts through physical later appends. An invalid suffix after its older resident cut still causes failure after 27 decodes and before any fresh catalog. Seven complete malformed-row variants separately cover schema/session/sequence, malformed JSON, missing model request, duplicate model response, and changed owner on both real backends. `OpenSnapshot` and `WriteCache` return the same error for each malformed fixture; neither publishes a catalog or cache value. Corrupt external JSONL payloads also fail, while a torn trailing line is neither read nor repaired.
- A synchronized test-only hook after the initial JSONL scan rewrites a pinned byte or appends a suffix. In both arms it triggers real `source_version`/revalidation; the real backend hashes the same full fixed extent twice, rejects the rewrite, accepts the fixed prefix with an appended uncommitted suffix, and neither publishes a now-stale catalog. SQLite uses a pinned transaction and has no such mutable-file hook.
- The byte-parity cases feed the same unchanged 49-record physical journals to both executables, not two separately generated inputs. Native request validation includes the real random live IDs; only independently generated response `snapshot_id` fields are normalized before comparing serialized response bytes. Persisted catalog and cache bytes are compared **as written** with no normalization (the write is given the same stable source ID in each run).
- Full native crate test suites run in debug, and targeted native cases also run in release, in both serde_json map layouts. See `verification.json` for matched counts, hashes, source pins and allocation results. An additional default-map release run repeats the same gates with separately regenerated physical fixtures in `repeat-release.json`.

## Measured Rust heap, not process RAM

All measurements bracket one cold `OpenSnapshot` in an isolated same-thread test. Fixture construction and disk files precede the scope. The seeded request and fresh service start inside the allocator scope; the net live balance is carried into the phase, with maxima and event counters reset. The measurement ends while the identity and service are live; all counted Rust owners are then dropped, and the meter requires zero live bytes. `requested` includes the full new request size for each realloc. SQLite's C allocator, allocator overhead, page cache, RSS/PSS and timing are **not** measured. These are cold *identity* requests, not measured Desktop startup or `OpenDisplaySnapshot` results.

| 120 turns, release | Peak Rust heap, stock → candidate | Requested Rust bytes, stock → candidate | Allocation calls, stock → candidate |
|---|---:|---:|---:|
| JSONL, default | 612,559 → 529,804 | 2,966,185 → 2,731,005 | 16,889 → 16,509 |
| SQLite, default | 546,767 → 482,375 | 1,263,550 → 1,048,586 | 3,416 → 3,057 |
| JSONL, preserve_order | 606,479 → 534,316 | 3,078,041 → 2,855,829 | 20,140 → 19,767 |
| SQLite, preserve_order | 596,047 → 476,799 | 1,359,914 → 1,090,094 | 3,451 → 3,057 |

The 120-turn fixture has 481 validated source rows: a user-history append, then typed alternating successful usage and direct context-window-error turns. Both arms measure the same physical source in each pair, for the model-heavy cases and the separate text-only control. The text-only control has identical allocation and watermark counters. The size of savings depends on model activity, not the size of transcript text alone. No retention improvement is claimed for results: live bytes at return were unchanged in the paired cases.

## Replay

Requires Python 3.11+, Git, a C toolchain for Ring and bundled SQLite, Rust/Cargo/rustfmt 1.95.0 Linux x86-64, the pinned source checkouts, and official crate archives. The source inventory validates all 184 files of the three crate roots and the two original locks. Within the replay workspace the Git dependency references are redirected to the exact checked local sources; a pinned isolated lock selects 157 registry archives with the exact Modules lock SHA-256 checksums. No build contacts the network.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --modules /checkout/Proteus-modules \
  --core /checkout/Proteus-core-0c1b7572 --work /fresh/private/work \
  --toolchain-bin /path/to/rust-1.95.0/bin --archives /path/to/official-archives
```

Repeat `--archives` for multiple directories. The verifier forces the leaves to compile separately, while reusing only dependency artifacts. It rejects a cached leaf artifact, mismatched manifest or entry source, and identical frozen executables. Test-only fixture and version-hook overlays are identical in both arms and are **not** in the product patch. [#579](https://github.com/Qweasd123tg/proteus-modules-dot/pull/579) and [#581](https://github.com/Qweasd123tg/proteus-modules-dot/pull/581) are previous published proof inputs, not dependencies of this fix. All six orders and reverse orders match the eight possible source subsets; this is source-only composition evidence, not a runtime claim for the composition.
