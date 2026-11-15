# Live runtime registry proposal

Source-only follow-up for known PR85 extension-multiview #2: separate new-surface default selection from all-live recipient inventory. Default selection/rehost policy is unchanged. Fanout and reload use one weak entity-keyed index.

**NOT COMPILED / NOT RUN.** No native UI, extension process, project test or live service executed. The second index adds memory/cleanup work and restored recipients may do additional legitimate work. #146/#147 composition is not runtime-qualified; missing rename-pair generation remains open.

Read [REPORT.md](REPORT.md), [INDEPENDENT-REVIEW.md](INDEPENDENT-REVIEW.md), [CHECKS.md](CHECKS.md). Patch: [live-runtime-registry.patch](live-runtime-registry.patch). The patch includes the proposed tests. Exact baseline Git blob identities are in `SOURCE-BLOBS.tsv`; retrieve baseline files from the pinned Desktop commit. Full source snapshots and raw execution logs are intentionally omitted.
