# Reuse tab IDs when activating an already visited pane tab

One common production hunk at crates/tabs/src/pane.rs on exact Desktop b6a7ec2d8d7e486c8aba01291aa8c89774c4cded and scoped cumulative Desktop through #447. Pane::show still checks exact membership first. The MRU pass preserves the order of nonmatching entries, removes every matching entry and appends exactly one. It now moves one existing matching String back into the kept history slot, allocating an ID only on first visit. It leaves the separate active String unchanged only when it already has the exact ID; a different ID still replaces the old allocation. No new owner, cache, persisted field or reserve.

## Focused evidence

- Source checks: 62 Desktop receipt hashes through #447, exact stock and sealed M150 tabs source. The cumulative projection uses only the #440/#444 tabs hunks; #447 does not touch the tabs crate. Only 488 KiB of initial source inputs staged; 11 exact locked dependencies.
- Four fresh arms (stock and cumulative baseline/candidate) each passed 72/72 actual tabs crate tests and 4/4 focused direct tests, from eight fresh artifacts. Four full traces match byte-for-byte, witnessing actual private MRU order in Pane Debug, exact pane/layout serialization and close fallback, pinned/preview replacement, Unicode, stale duplicate cleanup, active/first/restored cases and empty/missing controls. The probe calls real Pane and TabLayout methods with no native or modeled product shim.
- Scoped synchronous Pane::show allocation/reallocation requests and aggregate requested bytes, equal on stock and cumulative source tiers:

| Operation | Requests before → after | Requested bytes before → after |
| --- | ---: | ---: |
| 64 reselects of the remembered active tab | 128 → 0 | 3,072 → 0 |
| 64 alternating revisits to remembered tabs | 128 → 64 | 3,328 → 1,664 |
| 1 first visit, with preexisting history-vector capacity | 2 → 2 | 56 → 56 |
| 1 active after deserialize, but absent in history | 3 → 2 | 144 → 120 |
| 64 missing IDs or 32 exact active empty IDs | 0 → 0 | 0 → 0 |

The synthetic duplicate cases also preserved all non-target order: different active 2 → 1 requests, matching active 2 → 0. These are allocation counters for this method, not whole tab activation, redraw, long-term memory or a throughput claim. Native UI, terminal, PTY, app-server, network and remote operations were not run.

The single admitted run used the existing warm retained toolchain with one locked offline Cargo job and common build lock. Fences were 512 MiB target/staging, 256 MiB temp, 200 MiB growth, plus 32/8 MiB prelink reserve. verify.sh --prepare is source-only; --run requires separate sole-slot admission. cargo-provenance.json binds selected fresh artifacts, behavior.trace gives lengths/digests of the matching raw trace records, and work.log and evidence.log retain the scoped counters and observed fences.
