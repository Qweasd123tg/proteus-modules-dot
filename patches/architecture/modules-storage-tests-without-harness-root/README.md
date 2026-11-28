# Do not discover Core test fixtures for explicit storage-only Modules tests

Standalone Modules patch on `7274147162cb226f05df13a52b4a271fa5619313`. Verify `sha256sum -c SHA256SUMS` and apply `source.patch` in a detached checkout.

An explicit selection containing only `session-storage` and/or `proteus-session-storage-module` with recognized Cargo flags forwards directly to Cargo. Those tests create their own fixtures or use the executable built by Cargo; they do not read the extra Core checkout path. Cargo still resolves the same pinned Git libraries. Full, mixed, ambiguous and other selections use the previous fixture preparation. No test coverage, package format, runtime behavior or pin is removed.

See receipt.json for the traced native command, fallback test and exact source evidence.
