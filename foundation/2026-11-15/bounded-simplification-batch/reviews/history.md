> Publisher freshness note: original review below covers historical Core `bcbda443`. Both targets and the inspected current-only caller remain identical at batch base `a3b82a67`; fresh identities and patch checks are recorded in the common SOURCES/VERIFICATION. Its historical composition with the combined runtime candidate is not the recommended set; the current batch uses only the tuple split and excludes revision HOLD.

# Independent review: history-cache generation admission

Reviewed Core `bcbda4435534a296c707a1daa250813d692f68e1`, patch SHA-256 `f3e109e56e8b02355175d59061bf3ca4d0df04a7f7babf4f119dff9c4f2d2283`.

**Verdict: no source-level correctness blocker found in this bounded candidate. Suitable for source-only publication and targeted qualification, not a compiled, tested or benchmarked production result.**

## Snapshot and race reasoning

`Reader::open` observes `before`, opens the read-only connection, and reads the checked source row inside the pinned SQLite transaction. The stored `source` and `before` fields then remain immutable. The new predicate compares these two stored fingerprints only. It neither resamples the filesystem nor substitutes cached source for the live source.

If `source != before`, the old final conjunction is already false regardless of what happens during payload decoding. Early rejection in current-only consumers therefore does not discard a reader that the old predicate could subsequently call fresh. This also covers a cache generation that races ahead of the initial source observation: the old algorithm rejects that snapshot too. No retry or stronger freshness guarantee is introduced.

On accepted paths, `finish` still rereads the source after decoding. A source append during decoding remains a miss for current-only consumers; named stale reads retain the pinned old rows rather than being relabeled. `revision()` hashes/serializes the stored source fingerprint plus cache format and performs no filesystem observation. Moving it before payload decoding does not change the generation it names. The final source-read failure is still a miss even for named/display reads.

## Return behavior and fallback

`conversation` already returned only a fresh snapshot. `load` previously could return a stale tuple, but its inspected production caller `fresh_read_model` accepts only `Some((_, model, true))`. The new early `None` is therefore the same cache miss at that boundary. This reasoning is caller-dependent: a future stale consumer must not reuse `load` assuming all old return cases remain available.

The page condition retains all three policies:

- A specified revision must match the immutable cached revision; a matching old revision remains readable while the source advances.
- An unnamed current page requires both early equality and final freshness.
- Explicit stale display bypasses the current-only early rejection.

Wrong revision, malformed payload and invalid source are still cache misses. Payload/schema/checksum/row-count and workspace checks remain on every accepted read. Intentionally skipped checks on an already rejected generation do not expose unchecked data. Canonical fallback and the named-revision recovery error are unchanged. SQLite connection/transaction lifetime remains RAII-owned, including the new early returns.

`SessionReadModel::matches` was correctly retained: its second workspace observation occurs later than the header check and is not a redundant pure comparison of already captured values.

## Effect and limits

The work removed is concrete: stale-at-open conversation/model reads no longer decode full conversation/context/transcript payloads, and mismatched named transcript requests do not materialize rows of the wrong revision. This is not a LOC reduction or a measured universal speedup.

The new fresh-path fingerprint equality may traverse the blob inventory, so it should not be described as necessarily constant-time. Initial fingerprint inventory, source row decoding and accepted-path final scans remain. Named-page revision calculation still serializes/hashes the fingerprint, merely earlier. Measure realistic long-history stale reads and fresh controls before claiming latency, allocations or RSS improvements.

## Compatibility and validation

Independently retrieved the exact two touched files and current-only caller from the pinned upstream commit; Git blob identities and local bytes match. Also read pinned SourceFingerprint implementation, cache/read-model tests and app-server recovery caller/tests. Existing cache-opening/replacement gate, format/schema checks and writer logic are untouched. Known fingerprint-cap availability, cursor lifetime, precommit publication and crash recovery issues are not fixed or made newly safe by this patch.

Strict forward/reverse `git apply --check --whitespace=error-all`, actual isolated application, candidate equality and exact restoration passed independently. Applying this patch before/after the separately reviewed runtime-capture candidate produced identical combined source bytes. That composition result is structural only and does not endorse the runtime candidate's separate revision-semantic issue.

The existing page-order test covers wrong revision, stale matching revision, unnamed stale rejection and replacement. Recovery tests cover refusing to relabel a new source as a lost revision. The decode-race and damaged-cache tests exercise the shared Reader through the generic cache path, not every new early-return branch; they are useful controls but not a completed branch matrix. No test was executed. Rust/Cargo/rustfmt, HTTP, GUI, CI and benchmarks were not run. No new duplicate test framework is justified; qualify with the existing targets and extend the nearest behavioral case only if a concrete coverage gap is found.
