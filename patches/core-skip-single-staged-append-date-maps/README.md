# Core: skip per-identity date maps for a certified single text append

`source.patch` is the only patch to apply to [Core b2d2e6de](https://github.com/Proteus-harness/Proteus-core/tree/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14). The other diffs are previous, independent changes used to verify composition.

A completed, certified causal stage reports how many display records it wrote. If it reports exactly one, the renderer checks the decoded record: nonzero sequence, `HistoryMutated::Append`, no compaction or tool results, and every part is text. Every message and part in that one record has the same first durable date, so two timestamp maps can be left empty. The existing renderer still uses the date while producing the rows and still performs filtering, deduplication, visibility and live-turn checks. This does not change call dates or the handling of nonqualifying records.

The count is an optimization hint, not a validation shortcut. No read is skipped. The stage rewinds, decodes, runs callbacks, reads to EOF and checks its completed count as before. The stock nonzero sequence check still executes before the shortcut. A later callback clears the single-record mode; extra, malformed or incomplete stage data still prevents row return. A cache hit that bypasses stage render, a direct unstaged read, a multi-record stage, or a content shape outside the guard has no fast path.

## Measured on the exact staged scanner and renderer

The public [Desktop benchmark](https://github.com/Proteus-harness/Proteus-desktop/blob/f8cc40177ad3ab3d8ec36447a899332778f03268/examples/performance/native-history/run.py) invokes Core's [seeder](https://github.com/Proteus-harness/Proteus-core/blob/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14/crates/proteus-core/examples/session_index_fixture.rs) in a configuration that appends one batch of alternating user and assistant messages with four repeats of the specified Unicode text. The Rust harness lifts the actual message-construction expression and constructors, using deterministic UUIDs, then feeds one typed Append into Core's actual file-backed stage and display renderer. The pinned file-stage writer uses `tempfile`. The 5,000- and 50,000-message fixtures exercise the same seed shape, not a sum of many smaller records.

Requested-live allocation scope begins before the already-written file is rewound and includes reads, parse/decode, timestamp collection, row allocation, completion checks and row return. It does not include writing the stage, transport buffers, durable state or the worker. Same serialized rows and total requested-live bytes at return. Dropping the rows returns all tracked live allocations to zero.

| Fixture | Stock → R269 requested peak | #567+#569 baseline → add R269 | R269 difference at date collection barrier |
|---|---:|---:|---:|
| 5,000 rows | 17,453,592 → 16,912,888 B | 15,489,702 → 14,948,998 B | 540,704 B |
| 50,000 rows | 153,991,484 → 149,666,076 B | 100,748,162 → 96,422,754 B | 4,325,408 B |

The 50,000-row change is about **4.13 MiB** at this local stage, unchanged whether the two earlier patches are present or not. Their raw buffer release and text ownership gains are not counted as R269. There is no claim about full-startup peak, host PSS/RSS, or a particular owner's memory.

The optimized-build CPU guard uses process CPU time on a pinned core, two warm-up pairs, alternating order, and compares R269 against each of the two corresponding baselines. The single-16, 5,000 and 50,000 row cases and sparse mixed/multi-record control are gated at a candidate/stock paired median of at most 1.12 and paired 90th percentile of at most 1.25. Small/mixed values are from batches of 1,024/256 renders per sample; 5,000 uses batches of three; 50,000 uses one per sample. Stage writing and rearming the certificate are outside the timed interval. See `verification.json` for measured samples and ratios rather than attributing scoped CPU to an installed app.

## Reachability and failure behavior

The lift executes the real Core projected-open, local stage writer, snapshot scan and renderer. It exercises a typed projected-provider response, projected `None` and projection unsupported, both of which enter the fallback reader. The fallback's full journal validator/usage/context accumulation and the provider transport/worker are boundaries, not part of the compiled slice. Their fixture paths and pin checks do not amount to running the native Desktop benchmark. Direct unstaged rendering is checked without hitting the shortcut. A successful warm cache bypass is established from the unchanged caller, not timed or claimed as a benefit.

Before any row publication, the harness compares serialized rows and request order across all four arms and tests duplicate message and part IDs, Unicode and blank/multipart/hidden/zero-part messages, date extremes, live-turn exclusion, a plain reset, compaction, mixed tool/part history, committed model response, backwards clock and rehosting. A genuine stage is then perturbed to check wrong count, truncation, lack of LF, late parse error, extra record, real read error, early callback error precedence and the preserved zero-sequence panic. Returns on failed scans contain no rows. Hosted-card timing and standalone tool events are guarded out and source-audited; the mixed runtime fixture uses tool parts, not a separate host-card or standalone-event test.

The source-derived supplemental `provider-bounds.json` sizes the typed public shape. At 50,000, the exact fixture's record is 32,689,290 B. Independently adding the pinned no-model state envelope to the canonical array gives 32,689,149 B, 865,283 B below the built-in worker's 32 MiB state threshold. The record, canonical payload and per-stage size bounds are separate. These figures establish byte-cap plausibility, not an actual worker accepting the request or surviving other runtime limits. `module-pins.json` and `size-anchor-pins.json` document those external source anchors. The check can be reproduced with `python3 -B size-analysis.py --source /checkout/Proteus-core --rust-receipt verification.json`.

## Composition and reproducibility

[#567: release the last display-scan buffer](https://github.com/Qweasd123tg/proteus-modules-dot/blob/1b8b37fc4a622d6df32880e44cca64c2df89b3d7/patches/core-release-final-display-scan-buffer/source.patch) and [#569: move staged singleton text into rows](https://github.com/Qweasd123tg/proteus-modules-dot/blob/9d015bae8dc44b42a5dfc1e1418e83d0ef1dba3b/patches/core-move-staged-singleton-transcript-text/source.patch) compose without rewriting hunks. All six forward/reverse orders and all eight exact source subsets are checked. Native comparisons cover stock, R269 alone, #567+#569, and the three together, in both Serde JSON map modes and debug/release profiles.

Replay uses 42 pinned Core source paths, 47 checksum-matched official crates.io archives, and Rust 1.95.0 for x86-64 Linux. Git, Python 3.11+, and a local C toolchain for ring are needed. Build/test runs offline in the supplied fresh work directory:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --source /checkout/Proteus-core --work /fresh/replay \
  --toolchain-bin /path/to/rust-1.95.0/bin --archives /path/to/crate-archives
```

Use `--cpu <allowed core number>` to pin the serial CPU probes and `--desktop-source` to verify the optional local Desktop source anchor. Repeat `--archives` for multiple archive directories. See `SOURCE-PROVENANCE.json` for exact patch/source blobs and `verification.json` for the completed replay.
