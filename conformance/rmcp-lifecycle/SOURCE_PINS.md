# Source pins

Read-only inspection, 2026-10-25. No upstream server or test suite was executed.
Cargo.lock fixes all transitive versions/checksums (69 package entries including
this authored package). Direct crate archive bytes match their registry checksums:

| Crate | Exact version | Registry checksum = cached archive SHA256 |
|---|---|---|
| `rmcp` | `3.3.0` | `b88db56b8ae316560e9e868b6b978ea940f27cb883323fc90e07435e44158f5c` |
| `serde_json` | `1.0.154` | `e7e9cc8b1b85264074fbcc02a88680c4096b1e47df8f739dceb03bf482f04bd6` |
| `tokio` | `1.52.2` | `110a78583f19d5cdb2c5ccf321d1290344e71313c6c37d43520d386027d18386` |

Published rmcp archive VCS metadata: `3e636cab26c013eca5131103c03d20237f12c4df`,
path `crates/rmcp`. Archive checksum is authoritative for these inspected package
bytes; a repository commit alone is not a replacement for the published archive.

Proteus Core: `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`.
Codex: `970111f6cb62cc02fe36a82ea7d71b37a2889c97`.
Exact repository-relative files, immutable links and SHA256 values are in
[SOURCES.json](SOURCES.json). Repository observations remain source-derived. Actual SDK behavior is supported
only for the authored cases in the exact runtime receipt in VALIDATION.md.

The proposed workflow reuses the exact official checkout/upload-artifact action
pins from the already-reviewed parent publication workflow. This lane made no
remote write or independent action-version upgrade.
