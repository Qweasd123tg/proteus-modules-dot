# Borrow completed call IDs while normalizing workflow history

Exact base: [Proteus-modules at 331cfc20](https://github.com/Proteus-harness/Proteus-modules/tree/331cfc20bbaf821ab07de49868426da29ebdeb64), `workflow/coding-workflow/src/history.rs`.

The temporary set in `normalize_missing_tool_outputs` now borrows each existing result's call ID rather than making a new `String`. The locked SDK defines `CallId = String`; hashing and equality of the referenced IDs remain value-based. Both scans borrow the same immutable messages. The set is last used before any insertion, and the inserted rows still own their IDs. No result is consumed or shared into returned history.

The same payload-level matches, visibility and order are preserved. An unmatched call still gets the same synthetic request-only `aborted` result in the same position, not a record that the tool was executed. Existing successful or failed results remain untouched. This affects model-history normalization on the Coding workflow before sampling; it does not change checkpoint or provider behavior, compaction policy, or history persistence.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

The exact delivered artifacts for [#525](https://github.com/Qweasd123tg/proteus-modules-dot/pull/525), [#357](https://github.com/Qweasd123tg/proteus-modules-dot/pull/357) and [#366](https://github.com/Qweasd123tg/proteus-modules-dot/pull/366) do not touch this file: #525 is Codex context-overflow recovery, #357 is the scaffold/checkpoint suffix and its test, and #366 is resumed sampling ownership in host code and its test. None is a prerequisite or reapplied by this patch.

## Verification

Use the exact externally pinned files from `SOURCE-PROVENANCE.json`, under the `*.ref` names listed there.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc
```

The proof builds the complete normalizer and output-message helper from both exact source files with pinned SDK constructors and inert JSON/identity adapters. Rust 1.95 passed 7/7 in both debug and optimized modes, including the unchanged direct upstream ordering/idempotence test in both arms and 4,096 generated paired histories checked against a slow ordering/membership oracle. Native workflow integration, actual provider/host, and JSON serialization were not run. Full-file patch apply and reverse and the candidate's rustfmt check also passed in private scratch.

On a synthetic history of 125,000 rows (62,499 complete call/result pairs with independently owned 64-byte IDs, plus two user rows), the normalizer returns identical rows. Scoped allocator requests went from 62,515 to 16, with zero reallocations in both arms and summed requested bytes of 10,553,692 vs 2,359,516 in each build mode. These are fixture-specific allocator requests over the exact normalizer, not peak memory, process PSS or latency.
