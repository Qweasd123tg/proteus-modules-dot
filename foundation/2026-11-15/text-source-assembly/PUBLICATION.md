# Publication verification

Source-only assembly, alternative to original patches #115, #116, #119 and #124-on-119. Standalone #124 excluded. No upstream changes.

Publisher independently rehashed 19 source/input blobs; verified 14 target hashes in each of the three selected orders; repeated combined strict zero-fuzz dry-run, apply and reverse, including baseline restoration and new-file removal. No whole-tree or all-permutations claim.

25 retained proposed Rust tests: NOT COMPILED / NOT RUN. No runtime, project script, fixture, formatter or application executed. No CI PASS claim.

Raw logs and baseline/working source snapshots are deliberately not published. Relative local fields in provenance name unpublished verification inputs, not files provided by this bundle. REPORT.md and REVIEW.md are preserved byte-for-byte; their log references describe original private mechanical evidence. MANIFEST.sha256 covers only this sanitized public bundle.
