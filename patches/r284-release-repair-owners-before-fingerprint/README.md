# Release the repaired canonical model before the final source recheck

This is one ownership-lifetime edit in Core's Unix cache-miss repair. On a missing or invalid disposable history-page index, or a missing complete named transcript, the runtime validates and renders a complete model and then reopens the authoritative journal snapshot to verify that the original source did not change. The checker still needs the rendered rows, but stock also carries the just-repaired canonical history, usage, summary and prefix index through that final storage I/O.

The patch moves the entire rendered vector out of the successfully repaired model immediately, so the other owners are dropped before the final read. It does not alter the final OpenSnapshot/ReleaseSnapshot, the source/session/revision/content comparison, any projection or cache writes, their order, their errors, or the returned page/full-transcript capacity. The complete rendered vector remains live through the final check, even if a page caller will use only 50 rows. Invalid page offsets are still checked after the final fingerprint. Resident conversation reads, named/unnamed cache hits, and the separate project_validated_view path are not changed.

## Scope and measurement

This is not a whole-repair memory peak improvement. Earlier validation, rendering and cache-save phases can still overlap the same canonical and rendered data. This edit changes lifetime and does not remove these allocations. Proof covers a final synchronous storage request that could wait; it is not a measurement of OS RSS/PSS, a deployed worker's latency, or Desktop startup.

The local Linux x86-64 Rust 1.95 release harness uses exact source-bound implementations of transcript page, named transcript, rebuild, projected or strict snapshot opening, canonical validation, renderer, cache publication and fingerprint/release. It uses the real contracts and session-semantics crates and a typed fake only at the storage I/O boundary. See route-scope.md for the exact lift and instrumentation. The 5k and 50k histories use the upstream public seeder's text constructor and deterministic fixture IDs; they are synthetic, not real user journals.

The allocator measures requested Layout, not usable bytes or physical pages. A capture hook immediately after the actual cache save tags owners of the still-complete model by actual allocation address, size and monotonically increasing generation; realloc removes the old generation even on same-address reuse. Actual final OpenSnapshot and its conditional ReleaseSnapshot then check which captured generations are still live. Set backing layouts are found from in-allocation element addresses; no inference from HashSet.capacity. The report excludes unclassified ledger entries, fixture setup and diagnostics from the savings. The output compares rendered owners, buffer capacities, canonical/digest/prefix cohorts, fault ordering, row wire equality and publication artefacts.

Core donor: `b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`. Production preimage `696dfee0270d8825740121e2e85db971f017a8ea`, postimage `126a10d4bfa7e147e35fc2b657874ba2baceeb29`. No remote writes.

## Measured result

The projected and strict/canonical paths agreed for all three repair entry shapes (unnamed page, named page, named full transcript). The numbers below apply at the actual final snapshot open and conditional release in the focused harness. They count tracked nontranscript model owners only; the candidate has none of these original owners left at either request.

| Synthetic history | Stock nontranscript bytes, default | Stock nontranscript bytes, preserve_order | Stock allocations removed from this phase |
|---|---:|---:|---:|
| 5,000 rows | 4,084,185 | 4,484,185 | 10,008 |
| 50,000 rows | 39,528,737 | 43,528,737 | 100,008 |

At 50,000 rows, default's total includes 34,088,890 bytes of canonical message/part/text buffers, 2,097,152 bytes of ordered digests, 3,342,384 bytes of allocated UUID set layouts, and 311 bytes of summary owners. The separate known rendered cohort stayed at 54,092,610 bytes in default and 61,956,930 bytes in preserve_order, with the same capacity and all original tracked owners live across the recheck in both arms. This is earlier reclamation, not fewer allocated bytes over the complete repair.

In each feature graph, all 92 paired cases passed, with 73 paired final observations and two controls with nonempty genuine model context. The latter retained a 16-byte original context vector allocation in stock but not in the candidate. The route exercised both projected and strict record reads, named and warm behavior, cache publication failures, precheck/validation/renderer/prefix faults, final fingerprint drift and storage faults, and invalid-offset error precedence. See `GATES.md`, both raw JSONL receipts and both independent summaries.

Portable staging checked 158 pinned Core files, 152 locked registry archives and 8,573 archive members, both dependency-feature graphs, and byte-identical lifted sources. To replay offline with the pinned Core checkout, official crate archives and Rust binaries, use `python3 proof.py --core CORE --archives ARCHIVES --rust-bin RUST_BIN --work NEW_EMPTY_DIR --action run`. The portable recipe was staged independently; the recorded native execution used the verified shared build lane. Check raw run evidence independently with `python3 check_layout.py default.jsonl` and the equivalent preserve_order invocation.

## Raw receipt transport

The two complete JSONL receipts are stored as Base64-wrapped gzip to keep the Git packet small. Decode them before invoking the receipt checker directly:

```sh
for mode in default preserve_order; do
  base64 -d "$mode.jsonl.gz.b64" | gzip -dc > "$mode.jsonl"
done
sha256sum -c RAW-SHA256SUMS
```
