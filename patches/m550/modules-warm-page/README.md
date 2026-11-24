# Modules: verify canonical pages without building unused derived views

On the first `ReadRecords` against a provisional warm snapshot, or when that
snapshot must be revalidated, the complete fixed journal is decoded and verified.
The page used to build model-context and usage projections even though it did not
return them. This patch uses the same fold with both projections disabled for
`ReadRecords` only. Conversation/resume still build both views; `ReadUsage` still
builds usage without model context.

No validation or I/O is skipped. The same backend records, sequence/content
checks, fixed revision, source-version fences, terminal capture, pagination byte
budget, pending-record cursor, and durable guarantees are used. There are no
changes to storage format, contracts, locks or privileged operations. Not a
general page-cache proposal, and not counted as a change to another component.

**Exact baseline:** historical Modules M350 archive
`a04006ac24402104fc7366d6c41fd2090c7a8add508f28e0980522e0f98e70d1` (Git tree
`826088a9432dd024d7b1aa4ded490cb5608ff65f`). Only
`storage/session-storage/src/snapshot.rs` changes:
`c5b3e04616cca767364d508efc5e9a2f7015de37` →
`c914c39ff273c35d70fb547b85b8db311a2d544b`.
Strict forward and reverse apply checks pass. The independent integrator also
replayed together with the prior wave's unrelated #595 Modules patch.

**Native service gate:** exact pinned Core SDK source rev
`0c1b7572313230e5d123e95c722e1258a2e9ecd6` and Modules Cargo lock resolutions.
Rust 1.95.0 native debug, different freshly compiled test executables for each
arm, both default and `serde_json/preserve_order`. 100 existing service tests
and one new full public-service `OpenSnapshot → ReadRecords` regression passed
on each arm; the existing ignored benchmark remains ignored plus the separately
invoked same-corpus allocator test. This uses real JSONL and bundled SQLite
backends. The regression covers ordinary/terminal reads, exact response
contract and cursor, retry/reposition with a newer append, and nonempty
conversation/usage/before-turn context reconstruction of the pinned prefix.
Unchanged tests cover mid-read EOF mutation, bad blobs and SQLite pinned
transactions. Separately, an independent two-case sidecar passed both layouts
on both arms, including repeat rejection of an untouched terminal page over a
corrupt rich prefix.

**Allocator check:** one on-disk committed corpus per backend and size, used
read-only by all four executables after seeding. 0/16/128 alternating complete
and context-window-error model turns; initial/final ordinary history rows;
seven fresh provisional snapshot reads per case. All measured responses match
the exact serialized record-array SHA-256, and decoded-record and fingerprint
byte counts, on both arms of each profile. The measured thread-local
`StorageService::execute(ReadRecords)` boundary excludes fixture preparation,
request creation and response serialization. It does not include SQLite's C
allocator. Medians below include reallocations as requests and show extra net
peak Rust-allocator bytes above request entry, not PSS/RSS.

| 128 turns, default | Allocation/realloc calls | Requested bytes | Peak net live bytes |
|---|---:|---:|---:|
| JSONL first row | 18,644 → 18,242 | 3,142,461 → 2,934,977 | 536,651 → 496,238 |
| JSONL terminal row | 18,613 → 18,203 | 3,139,676 → 2,916,232 | 535,491 → 482,190 |
| SQLite first row | 4,282 → 3,865 | 1,311,457 → 1,101,261 | 536,501 → 492,557 |
| SQLite terminal row | 4,279 → 3,872 | 1,307,543 → 1,096,995 | 532,589 → 488,293 |

Across both layouts all 8 rich cells show lower net peak (29,432 to 53,301
bytes less) and lower requested bytes (195,684 to 223,444 less). Measured
zero-model controls show identical medians. At 16 turns the directional
allocation-count/requested-byte control still improves; the small net-peak
differences are not claimed as a robust win. Runs are allocator/durable I/O
checks, not controlled wall-clock latency; raw times from the semantic test must
not be treated as a benchmark. No app launch, GUI, worker RPC, model provider,
or 50k no-model RSS regression claim.

**Apply:** only `source.patch` is the product diff. Use `git apply --check` then
`git apply` from the historical Modules checkout. `warm-page-proof.rs` is a
test-only fixture, not part of the production diff.

**Portable verification:** with pinned Rust 1.95.0, the full canonical M350
Modules source archive, the authenticated Core source archive for the pinned SDK
rev and a directory of verified vendored crates:

    python3 proof.py --modules /path/to/Modules-M350-source.tar.gz \
      --core /path/to/Core.tar.gz --vendor /path/to/vendor \
      --work /path/to/fresh/work --target /path/to/empty-target

It checks the archive pins, all 184 staged SDK/module source files, and vendored
registry versions/checksums against the product lock. Appending `--prepare-only`
checks the inputs and patch without building. The portable builder cleans this
module's outputs between arms so Cargo cannot recycle a same-name prior
executable. Captured receipts use distinct direct rustc native debug binaries
linked to the already authenticated exact pinned SDK/registry dependencies;
portable Cargo runs in release and therefore may report different exact counts.
