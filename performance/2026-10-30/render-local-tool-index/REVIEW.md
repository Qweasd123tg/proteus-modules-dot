# Independent source review: render-local tool-row index

No bounded source blocker found. Reviewed Core
`befd30516aefa6f0a0ad5db9924ad4957160b8dc`, patch
`05-render-local-tool-row-index.patch`, SHA-256
`0b1396162dd421237731e9ac33b62dcf39815fe76c75c0cddebc6c36d4c6ed27`.

## Equivalence argument

`TranscriptRows::push` records every tool-bearing row, including hosted cards
and standalone result fallback cards. Inserting an existing ID overwrites its
index, exactly matching the previous reverse scan's last matching row. A later
ordinary call with the same ID supersedes earlier hosted/result rows as before.
The index does not alter journal seen-call/seen-result/seen-part filtering.

Results change status, result and metadata, not call identity or row position.
Allowed resolution changes effective_args; denied resolution changes status and
reason. Neither invalidates the index. Image attachment and timestamp updates
also preserve identity/position. All production row insertion routes use push;
there is no reorder, truncate, remove or direct raw-vector insertion. The vector
is moved out only after final rendering, when the lookup is no longer used.

The existing non-compaction Replace reset now clears rows and lookup together,
as well as the unchanged dedup sets. Compaction and excluded live Replace keep
their prior semantics. No index survives a rendering invocation or is stored in
session/cache. The unchanged replay-frontier tests use public render entrypoints,
not the old internal Vec type; checked current blob
`0061e3ec2fbc1d0fc9ecd8c4adfb9af6ee2857dc`.

Citation search is deliberately not indexed by call identity: it still finds
the last currently eligible name/provider_hosted row and then checks its array.
Replacing metadata with null/non-array or removing hosted eligibility therefore
retains existing fallback/no-fallback behavior. This avoids an easy incorrect
extension of the optimization. Image grouping and tool interruption finalization
remain unchanged.

## Regression-source review

New direct expectations cover delayed results across interleaved text, timestamp
preservation, duplicate hosted/ordinary identity, result metadata replacement,
citation array/null/eligibility behavior, reset with late standalone results,
and latest-row allowed/denied resolution. Existing borrowed-part tests only
change their access to the owned rows. Existing Replace/live/compaction replay
fixtures remain intact. No executed test success is asserted.

## Independent static checks

- Rehashed frozen patch to the SHA-256 above.
- Strict forward/reverse git apply with whitespace errors rejected; forward
  candidate and restored baseline compared byte-for-byte with author trees.
- Installed rustfmt 1.95.0 toolchain --check, edition 2024, skip_children=true:
  seven changed/new Rust sources passed.
- Read all changed production/test/doc sources and checked helper call sites;
  no omitted raw-Vec callers found in the affected modules.

Cost is one render-local String key and row index per distinct call identity,
plus HashMap capacity. This removes repeated reverse scans for results and
resolutions, but is not a benchmark or universal memory reduction. Citations
still scan. No tests, project code, Cargo, builds or CI were executed. Compilation
and applicable transcript/journal executable gates remain required.
