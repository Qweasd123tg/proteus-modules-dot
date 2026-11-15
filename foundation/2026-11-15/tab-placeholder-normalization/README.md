# Tab placeholder normalization proposal

Source-only follow-up for known PR85 D5-2. Reconcile automatic empty panes after collapse/flatten against their final siblings, using existing share-transfer and focus rules. No repeated whole-tree normalization or new model framework.

**NOT COMPILED / NOT RUN.** Eight proposed Rust tests are not fresh runtime evidence. No native UI or preferences-file test was run. The added phase has sibling-scan/vector costs; this is not a LOC/performance reduction claim.

Read [REPORT.md](REPORT.md), [INDEPENDENT-REVIEW.md](INDEPENDENT-REVIEW.md), [CHECKS.md](CHECKS.md). Patch: [tab-placeholder-normalization.patch](tab-placeholder-normalization.patch). The patch contains all candidate changes and eight proposed tests. Recover baseline files from the pinned Desktop commit using SOURCE-BLOBS.tsv; full source snapshots are intentionally omitted.
