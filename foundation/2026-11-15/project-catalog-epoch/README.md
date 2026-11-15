# Project catalog epoch admission

Source-only proposal for known PN-1 on Desktop
`7eaf70c67dabba8595d98029c875ffc3f59209ad`.

- `project-catalog-epoch.patch`: one production file, +30/−2 lines.
- `REPORT.md`: invariant, exact scope, limitations and verification.
- Source snapshots and the applied candidate are intentionally not published.
  Reconstruct `sources/` from the pinned Desktop commit using the paths in
  `SOURCE-HASHES.json`; verify each Git blob hash. Copy sources to `candidate/`
  and apply the patch there before running the text generator.
  The two generated harness files are included for inspection.
- `regression/`: 7 proposed std-only Rust callback controls with mechanically
  extracted baseline/candidate production methods. **NOT COMPILED OR RUN.**
- `INDEPENDENT-REVIEW.md`, `PRE-RUN-REVIEW.md`: independent source reviews.

The candidate rejects old-generation project catalog results before mutation,
and re-reads only for the still-current navigation. It does not fix every pending
deletion/creation race or establish production readiness. See the report before
applying. Do not confuse successful text extraction/patch checks with Rust tests.
