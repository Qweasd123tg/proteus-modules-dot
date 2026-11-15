# Portable update serialization candidate

Known [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85) release-manifests issue 2, not a new finding. See [REPORT.md](REPORT.md), [patch](portable-update-serialization.patch), and [independent review](INDEPENDENT-REVIEW.md).

One cooperating-writer lock spans default-base snapshot through publication and archive. Production diff +21/-1; waiting includes complete build/archive time. Explicit external `--base` is not a merge. Archive failure after publication does not roll back the bundle.

Evidence: Python 3.12.14 synthetic baseline expected old/new failure; six candidate tests pass with fake builders. No real builders, installs, permissions changes, Rust, benchmark, or full release gate. Upstream is untouched; this delivery repository contains a proposal, not an installed fix.

Publication verification recomputed every original package hash and five Git blob hashes, strictly applied the patch in a separate copy, and compared all four affected files byte-for-byte. No tests were rerun during publication. Source snapshots, disposable runtime copies and raw logs with local paths are intentionally omitted; TEST-RESULTS retains original log hashes as provenance, not downloadable evidence. Reconstruct pinned sources and apply the patch to reproduce the focused suite; the report describes the isolated driver contract.

PUBLICATION-MANIFEST.json covers only delivered files. It is separate from the original package manifest.
