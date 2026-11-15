# Git panel tab ownership: source-only proposal

See [REPORT.md](REPORT.md), [independent review](INDEPENDENT-REVIEW.md), [patch](git-panel-view-state.patch), [actual checks](CHECKS.md), [source blob catalog](SOURCE-BLOBS.tsv) and [measurements](MEASUREMENTS.json).

Repairs the ownership mismatch already documented in [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85), git-view-state #1. Per-view selection replaces a session-shared scalar; read caches stay shared. Production +16/-8 across two files. Eight existing direct test calls adapted; six proposed tests NOT COMPILED / NOT RUN.

No upstream source is changed by publishing this package. Rust/build/tests/native UI/wire/CI are NOT RUN. This is not a production-qualified fix, a new finding, or a measured performance gain. Hash-alias #2, broader native/session reset coherence and integration with [PR146](https://github.com/Qweasd123tg/proteus-modules-dot/pull/146) remain unresolved.

Publisher independently verified all 19 source blobs against the pinned remote trees, strict forward/reverse apply checks, and applied-byte equality with the reviewed candidate. Full source snapshots, raw logs and private paths are not included. SOURCE-BLOBS paths identify upstream inputs, not bundled files. SHA256SUMS covers only this public package.

Report's historical link was changed to a pinned repository URL for publication; patch and independent review are unchanged. Mechanical integrity is not behavioral success.
