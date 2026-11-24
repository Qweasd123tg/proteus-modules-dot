# Core: reserve the input buffer for a large single staged display record

Exact Core M387, same 1,100-file Core tree as M384 (Wave8 Core was held;
the accepted Wave8 changes are in the other repositories). Only
display_records.rs changes. Distinct from #614 subprocess newline framing,
#606 decoded per-row release and #626 historical cache compression: the
changed owner is the raw line of a local anonymous render spool.

An optional exact-size buffer hint comes from the successful capped writer's
record count and bytes already accepted, including the delimiter. The
hint is retained only for one record strictly over 4 MiB and at most
64 MiB. Failed write or flush cannot yield a stage. No metadata call or
additional I/O; no new limit on accepted records or bytes. The original
rewind, read-until-LF, incomplete-delimiter error, JSON decode, callback,
EOF and exact record-count verification remain. Allocation refusal falls
back to the same incremental growth. Empty, small, multiple records and
larger outliers retain the ordinary path. The trusted hint may reserve
earlier if the private file is later corrupted. Capacity is released before
the final large-record callback exactly as before.

## Native evidence

The actual M387 Stage writer/reader is compiled as a selected Rust module
and exercises real anonymous files using the exact Contracts/serde
dependencies. The operation meter covers only the raw allocation inside
reservation/read_until; the JSON decoder and callback are outside it.
Each 50k fixture is replayed twice from the same file, as staged readers
are rewindable. Per-scan figures in both JSON layouts:

| Single staged record | Raw length | max requested Vec capacity before → after | Raw allocation requests before → after | Reallocations before → after |
| --- | ---: | ---: | ---: | ---: |
| 50k ×4 | 32,689,292 B | 33,554,432 → 32,689,292 B | 67,100,672 → 32,689,292 B | 12 → 0 |
| 50k ×5 | 37,389,292 B | 67,108,864 → 37,389,292 B | 134,209,536 → 37,389,292 B | 13 → 0 |

The stock allocator did sometimes return a different address while growing
the raw line; the candidate had no growth. An address change is not
evidence that the kernel copied all old bytes. Requested capacity is not
physical memory, PSS, or start-up peak, since spare capacity need not be
resident. Neither fixture left a raw buffer at the final callback.

One compiled cutoff unit test/layout verifies count and both bounds.
16 direct A/B controls/layout include actual 4 MiB boundary triplet,
empty/small, escaped Unicode, forced optional allocation refusal,
valid trailing record and post-callback count rejection, callback error
precedence, missing LF, invalid complete JSON, legitimate multi-record
history, actual read-only-file flush failure, and exact/one-byte-over
writer budgets. Replay SHA, callback position/order, typed errors and
unchanged normal multi-record allocation metrics are checked independently.

A second native exact-source harness runs the selected Core startup,
stage, renderer, prefix and cache functions over a typed in-process storage
boundary. Its 65 paired controls/layout include projected and strict 50k,
multi-record strict replacement, stale/invalid prefix control, cache/
HEAD/named-page faults and render fallback. It verifies page and header
content, operation order and existing integrity checks. HashSet iteration
order of unordered identities is normalized; ordered canonical digests
are independently checked during persisted prefix readback. No installed
Desktop/worker launch claim is made by this harness.

## Scoped timing (not startup or PSS)

CPU7-pinned isolated processes in ABBA order, two processes per arm, seven
samples after one warmup each. Prebuilt identical spool bytes, repeated
rewind and normal parse on warm file pages; no worker, renderer, prefix
hash or cache packing. Raw time includes reserve and read_until operations;
full scan additionally includes JSON decode and disposal of the decoded
record. The allocator instrumentation is disabled within this timed scope.

| Layout | Fixture | Raw scan before → after | Full native scan before → after |
| --- | --- | ---: | ---: |
| default | x4 | 20.98 → 13.17 ms (-37.2%) | 103.74 → 86.62 ms (-16.5%) |
| default | x5 | 30.70 → 22.74 ms (-25.9%) | 126.50 → 114.09 ms (-9.8%) |
| ordered | x4 | 22.52 → 20.31 ms (-9.8%) | 114.37 → 109.25 ms (-4.5%) |
| ordered | x5 | 29.71 → 21.97 ms (-26.0%) | 128.05 → 117.47 ms (-8.3%) |

Native proof archive retained separately, SHA-256: `1c79da494ea146d969b7c32a5490462d605b04feaa45bda3d1850edeea199c19`.
