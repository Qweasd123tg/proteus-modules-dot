# Modules: move history Text into ReadDisplayRecords replies

**Dependency:** exact #618 (OpenDisplaySnapshot text ownership). On the
negotiated `ReadDisplayRecords` branch only, the worker now uses that same
message encoder for `HistoryMutated.messages` in a typed record-page reply.
It moves owned Text buffers into the SDK's required JSON Value. The pinned
Serde serializer still emits the record, page and individual message shells
and their key order; the optimized fields replace existing slots. Non-history
records, other part kinds, arbitrary metadata, and all other operations retain
their existing behavior. No SDK or protocol change.

The existing `StorageService` still owns first-page sizing, canonical checks,
snapshot identity, staging, byte/record caps, all cursors and the durable
journal. The pinned SDK still owns protocol authorization, negotiation errors,
lineage, cancellation, output-limit preflight and stream framing. This patch
does not change #618's OpenDisplaySnapshot wire shape. The regular canonical
`ReadRecords` operation is not selected by the new branch.

**Base:** complete exact M376 Modules Git tree
`6f0ea35d5761c8726606f95dbe49dfe9aba48331`, 610 files, archive SHA-256
`994628655562ad0d3808c712742a0fd009c5962690fbe37d9c74f6337004e0d0`. All files
and modes independently match a reconstruction from M372 plus exact #618.
Only the storage worker's `main.rs` and `display_reply.rs` change. Dependency
on #618 is deliberate. Independent strict rollback passes; post-tree
`01dff7bfe0680458496b25f8be1b95ddc96f90c1`. Exact pinned Core SDK remains
`0c1b7572313230e5d123e95c722e1258a2e9ecd6`.

**Genuine worker and same-source tests.** In each backend, actual worker
Create/AcquireWriter/Commit/ReleaseWriter seeded one immutable no-model
50,000-message Append and a separate three-mutation case with 3,500
messages per record. Fresh worker subprocesses checked both sources with
old SDK under default and preserve_order serde_json. The single oversized
display record remains a single record above the nominal 4 MiB page cap,
with empty terminal read afterwards (32,689,942 wire bytes for JSONL and
32,689,945 for SQLite in this fixture). The 3-by-3,500 case forces pending
rows across the nominal byte cap, monotonic continuation and ordered
rewind/retry. Exactly the generated snapshot UUID is normalized for the
paired wire digest; RPC ids and map byte order are otherwise retained.
The retry check separately normalizes only the differing top-level
request id. The valid JSONL large page passes at the exact configured
wire frame limit and one byte below produces the original SDK error
with no partial response. Exact before/after denial without the feature,
invalid record limit, malformed request, cursor beyond snapshot and
altered snapshot identity are checked too. Both original worker process
tests pass per arm/layout. A separate serializer equivalence test covers
mixed parts, Unicode/escapes, empty Text, nested metadata and a non-history
record.

**Allocator evidence for the single large Append.** Both Rust map layouts
move all 50,000 input text buffers instead of copying any of them.
19,688,894 requested bytes and 50,000 allocation calls are removed during
conversion. The meter starts with an already built typed page and stops
as its JSON Value is returned. It tests two independent typed input paths:
re-reading the actual produced worker frame and decoding a live native
ReadDisplayRecords through the same accepted StorageService.

| Input and serde_json mode | Peak net live Rust bytes during conversion, stock → candidate |
|---|---:|
| Actual frame replay, default | 157,894,797 → 130,205,706 |
| Native typed service page, default | 157,894,797 → 106,206,186 |
| Actual frame replay, preserve_order | 137,893,497 → 108,204,446 |
| Native typed service page, preserve_order | 137,893,497 → 78,205,046 |

The supplied inputs can have different original backing capacities; peak is
relative to conversion entry, not process memory. The JSON Value remains
materialized and validated by the unchanged SDK. These measurements are
not product RSS/PSS, duration, disk/parse savings or whole cold-path claims.

**Reproduce.** Only `source.patch` is the product diff. With pinned
Rust 1.95.0 and a verified Cargo vendor:

    python3 proof.py --modules /path/to/Modules-M376-source.tar.gz \
      --core /path/to/pinned-Core.tar.gz --vendor /path/to/cargo-vendor \
      --work /path/to/new-work --target /path/to/new-target --prepare-only

For a full run omit `--prepare-only` and supply either `--manifest`
(pointing to the shared live fixture journals) or `--seed-frame`
(the genuine 50k no-model OpenDisplaySnapshot fixture frame from the #618
proof). This creates test fixtures, not product or user data. The proof
builds both worker arms from the same unchanged old SDK, runs paired
stdio policy/byte gates and the allocation witness. The captured tests
used four distinct real worker executables with verified native dependencies.
