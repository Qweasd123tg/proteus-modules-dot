# Delivery boundary

This package publishes a source-only proposal for known PR85 D5-2, not a live fix. Upstream repositories are unchanged. No raw execution logs, private state, full source snapshots or historical fixtures are included. README/REPORT have been adjusted only to make these omissions explicit; the independent review hash references identify pre-publication prose. Patch bytes are unchanged.

Publisher rechecked all 19 Git blob identities and SHA-256 values against the pinned tree, strict forward/reverse git apply, zero-fuzz patch application and all three resulting candidate files. Eight Rust tests remain NOT COMPILED / NOT RUN; native UI, preference reset/restart and performance are not qualified. No CI success is inferred from publication.

Recover the baseline from Proteus-harness/Proteus-desktop at 7eaf70c67dabba8595d98029c875ffc3f59209ad; SOURCE-BLOBS.tsv lists paths and identities. Apply tab-placeholder-normalization.patch from that checkout root, then compile/run the real tabs tests before adoption.
