# Checks and limits

Performed as text/source bookkeeping, not project execution:

- Fresh start/end refs match for Desktop 7eaf70c, Extensions f82b3ad and delivery d2095a9.
- 21 source/document files match the pinned recursive-tree Git blob identities and SHA256 entries.
- Historical document-refresh report matches delivery blob 93ca636787b86d6aaa1a1646c336915306b2fa84.
- Desktop base is original source plus the preserved PR146 navigation-bootstrap patch, applied with zero fuzz. Extensions base is original source.
- Both new patches pass forward and reverse git apply checks with whitespace=error-all.
- Both patches applied with patch --fuzz=0 in owned reconstruction copies; all 23 reconstructed source/doc/test files match candidate bytes.
- The edited wire fixture parses with Python ast.parse; manifest JSON parses and the new feature string appears once in Files required_features and Desktop FEATURES. No fixture code or project script was executed.
- Independent exact source review found no blocking defect in the two candidate hashes.

Not performed:

- Rust compilation, rustfmt, unit/integration tests, native GPUI window, actual timer/HTTP reads, the wire suite, portable build, installations, provider calls or benchmarks.
- Rust/Cargo/rustfmt are absent from PATH; no toolchain was installed.
- PR146's historical generated stub harness was not adapted or rerun. New native-helper signature means that harness must be adapted before reuse.
- No full combined qualification with PR144 or PR146–149.

New Rust tests are proposals only. A text apply check is not a compiler or runtime pass. Upstream repositories and real data are untouched.
