# Borrow arguments while writing the remote display cache's tool index

On an accepted transcript row, the old cache writer makes an owned `AppToolState` for the duration of `write_content`. That clones the ID, name, status and both JSON argument trees before the existing size check and content-addressed write. The patch presents the same five fields as references to the existing private compact representation. The original transcript still owns its data. The byte-limit check still runs first, the serializer still makes the owned JSON cache value that storage needs, and the name still gets cloned for the index. There is no new cache format, public type, storage operation, or change to tool execution.

Target: [Proteus-core, b2d2e6de](https://github.com/Proteus-harness/Proteus-core/blob/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14/crates/proteus-core/src/core/session_store/remote/view/cache.rs). Only `update_tools` and the private `CompactTool` declaration change. The decoder's default type arguments remain `String` and `serde_json::Value`. Do not use the strict wire-state decoder to rebuild from full transcript pages: those legitimately contain result, metadata and terminal fields. The five compact fields deliberately mirror the public DTO; if its field order, optionality, names or Serde attributes change, review this mirror and rerun wire parity. No `unsafe` in the change.

## Invariants exercised

The native executable compares stock and candidate in the same process. In both Serde map layouts it compares final values, method results, index contents, and ordered storage operations; ordinary cases include the entire serialized cache request and persisted bytes, not just Value equality. It checks the persisted field order under `preserve_order`, the explicit `effective_args: null` when absent, and that input transcript bytes do not change. A present JSON null in that slot also persists as null and thus decodes as Rust `None` on both arms. The canonical ETag comes from Core's real Ring SHA-256 code.

* Cold `save_model` on 151 typed rows builds a real packed historical section before publishing the header. Direct `tool_state` reads and the fallback to `rebuild_tools` exercise the real page/pack reader. Only exact literal `failed` and `denied` rows are skipped. The last accepted row wins even if the newest row was denied. A repeated cache hit causes reads but no writes.
* A missing header index key returns a successful empty state without repair. A referenced but missing, corrupted or wrongly shaped cached value triggers reconstruction. A valid state with a different name or rejected status returns no result without repair. Failing page reads, partial index writes, missing ETags, unexpected transport responses, source changes and best-effort header publication are checked against stock. No stronger rollback is assumed.
* The existing-header/suffix case uses the production append, index-update and publish functions. The exact cold and incremental call sites are pinned. The incremental projection method, renderer and full-fallback orchestration are **not** run end to end.
* A name map crossing 16,384 is rejected **after** the admitted calls have written and mutated the map; a failed write leaves the previous same-name digest intact. Calling the index helper directly, a compact JSON payload of exactly 64 MiB succeeds; one byte more fails without even a cache read. Large-case evidence checks stored payload, size and digest rather than capturing huge request bytes in a log.
* The 1 MiB nested argument plus 2 MiB nested effective override is accepted in a separate real cold save, and its persisted and independently retrieved state match the typed stock DTO byte-for-byte. All argument strings are generated synthetic data.

## Requested allocations, not process RAM

Release Linux x86-64, per-call counting allocator around `update_tools` with a fresh map and in-memory transport. The original transcript is built beforehand; store payload, hash and recording overhead within the scope are included in both arms. “Peak” means maximum sum of live *requested* heap bytes in that scope; it does not include allocator arena slack, stack, prior fixtures or unrelated processes. Final live bytes are zero after clearing the in-scope indices/store/log. Totals by layout are in `verification.json`.

| Default-map input | Stock peak, B | Borrowed peak, B |
|---|---:|---:|
| Small accepted integer | 2,404 | 2,385 |
| 1 MiB nested arguments, no override | 2,103,522 | 1,052,944 |
| 1 MiB arguments + 2 MiB override | 6,301,788 | 3,152,077 |
| Oversized argument rejected before storage | 67,108,998 | 124 |
| 50,000 text-only rows; or one denied tool | 0 | 0 |

**Whole cold cache save, same accepted 3 MiB row:** measuring the pinned `save_model` call with its transcript pages, compact index and published headers (in-memory transport, default map), peak requested bytes fall from **9,455,760 to 6,327,222** (3,128,538 fewer, or 33.1%). Allocation traffic falls from 9,483,020 to 6,333,310 bytes; 473 calls become 442, with 13 reallocations unchanged. This is a synthetic one-tool cold cache save, not the process startup or an external storage service.

The large accepted index-helper case also removes 31 allocation calls on the default layout. The over-limit figure is a **helper-only boundary control**, not a reachable cold/append saving: both production callers write the larger full transcript row first and reject it at the page limit before invoking this helper. Neither text-only history nor a denied row reaches the changed path. No measured change to end-to-end startup, timing, retained RAM, or process RSS is claimed.

## Offline replay

Requires Python 3.11+, Git, a C toolchain for Ring, the pinned Core checkout, Rust/Cargo/rustfmt 1.95.0 for x86-64 Linux, and official archives for the 38 packages in this proof's lockfile. Each archive is checked against the original Core lock. No build or verification command contacts the network.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --source /checkout/Proteus-core \
  --work /fresh/replay-directory --toolchain-bin /path/to/rust-1.95.0/bin \
  --archives /path/to/official-crate-archives
```

Repeat `--archives` for separate collections. The verifier validates 23 pinned source blobs, applies/reverses/reapplies this one-file patch, checks its formatted postimage and builds with `--offline --locked`. It runs native debug and optimized binaries in both `serde_json` layouts and the allocation checks in each optimized binary. The comparisons are per map mode: physical request bytes may legitimately differ *between* layouts, while stock/candidate must agree *within* each layout.

This is an exact-source **slice**, not the native Core workspace or a live remote storage worker. Source lifts retain the operative cache/size/Serde/Ring/pages/pack code and actual tool, transcript, header, summary, session and usage DTOs. The read/write storage variants use the original fields; a recording in-memory store supplies the responses and journal snapshots. Unused request variants are omitted; empty canonical/context histories use placeholder item types, summary generation for empty history is substituted, and prefix persistence is deliberately not entered. The full desktop, worker, journal validation, execution and policy paths were neither changed nor benchmarked.
