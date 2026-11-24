# Core: consume decoded Append history in the temporary strict recovery fold

A restarted host can receive a single legal large Append via ReadRecords
when the backend cannot form a display projection within 32 MiB. The old
temporary recovery fold deep-cloned that record's canonical messages into
its history before writing the original record to the private display spool.
Both copies were simultaneously live. Validate the appended slice in the
same order first, let its observer stage the identical accepted record,
then transfer its existing owners. The first Append moves the outer Vec
too; later appends extend the existing history by move. There is no extra
storage read or materialized copy, and normal Rust COW rules remain for
shared state.

The envelope, record uniqueness, execution and turn binding, revisions,
scope, stable part identity, result binding and ordered active-ID collision
checks are preserved. The observer is not called on a rejected operation.
The consumer is a **temporary read fold** and discards it on error; like
the old validation state, it is not a rollback or reusable state on error.
The durable writer's borrowed path stays in place. Every non-Append follows
the same borrowed reducer; its valid observation occurs at the same boundary.

No projected snapshot, history/version/cursor cap, provider/worker route,
display spool serial form, paging, renderer, output fallback or privilege
changes. In particular this does **not** remove simultaneous typed
OpenDisplaySnapshot state and the second ReadDisplayRecords wire payload:
within the existing contract that would require spill/reparse or a
different two-phase worker protocol, neither of which is included here.

## Evidence

Exact complete M372 Core baseline and strict whole-tree forward/reverse
replay. Before/after genuine Rust 1.95.0 Semantics library suites compiled
with exact M372 Contracts, exact locked registry dependencies and appropriate
Serde feature closure: 19 and 21 passed, respectively, per map layout.
New tests verify first and later Append owners, and compare competing
duplicate/schema/sequence/scope/stability errors and observer cardinality.

The additional exact-source native lift invokes actual host record
acquisition, strict validation, display staging and projection/cache
entry points through a fixed typed in-process storage adapter. It validates
the same request and response byte/identity constraints; the real worker
process, pipe, or entire application is not replaced by a performance
claim. 58 controls + 2 large scale + 2 multi-record cursor/journal cases
per layout. Compared all emitted results, page/header hashes, journal
source/operation order, stage certification and full output fallback.
Late duplicate stops before staging that record and emits no cache writes;
old prefix fingerprints are identical after two valid appends. Projected
50k ×4 bypasses the optimized fold.

For strict 50,000 ×5 text in a single valid RecordPage, the meter observes
actual System allocation generations. Just before staging the fully
validated intact record:

| Feature layout | Fresh live requested bytes since the fold began, stock → candidate | Original text owners transferred into canonical history |
|---|---:|---:|
| default | 76,278,554 → 37,429,576 | 0 → all 50,000 (24,388,890 B) |
| preserve_order | 80,197,746 → 37,775,600 | 0 → all 50,000 (24,388,890 B) |

The original outer Vec and all nested parts Vecs also transfer in the large
initial append. These are local tracked allocation requests, not a global
peak or resident bytes. Fresh totals include active/known index costs
and may vary with map seed; transfer of original owners is separately
verified. Earlier decoder and projected overlap are unchanged. Do not
sum this with #603 or #606 across different phases or infer the observed
695 MiB from any of these measurements.

## Replay

Strictly apply source.patch after M372. The native witness package
contains exact source-lift generation, observer, adapter, run scripts,
source pins and complete JSONL control/scale/frontier logs. The build
files use the earlier independently pinned Cargo release dependency
closure for exact Contracts; native rustc separately builds both actual
M372 Semantics trees. Build and run locally with the verified frozen
dependency registry, Rust 1.95.0 and both map modes. The previous
benchmarked exact Cargo builds are dependencies only; no binaries are
embedded in this packet.
