# Caller-owned bundle path identity

Known PR85 build-portability issue #1, delivered as a standalone Core patch, not a new finding. Production delta +2/-1. The destination is resolved in caller cwd using the existing target-dir policy before the child cwd changes.

Observed evidence: Python 3.12.14 synthetic command-construction gate, baseline one expected assertion failure, candidate 5/5 passed. Child subprocess and source resolver mocked. Independent source/evidence review and strict patch application passed. No packager, Cargo, real CLI, installation, production runtime or benchmark was run. Upstream repositories are unchanged.

See [REPORT](REPORT.md), [patch](module-bundle-path.patch), [test summary](TEST-RESULTS.json), and [independent review](INDEPENDENT-REVIEW.md). Patch applies to Core bcbda4435534a296c707a1daa250813d692f68e1; Modules downstream source was read at c035142558f0fca43e9772fc0e50ca293abf1531.

Publication note: the report and reviews describe the original evidence workspace. Source snapshots, disposable runtime directories and raw logs are deliberately not distributed. Their hashes remain provenance only; public package hashes are in SHA256SUMS. To reproduce, obtain the exact pinned Core build_module.py, extract the new test from the patch, and use the reviewed driver with the supplied expected hashes. No existing suite or CI success is asserted.
