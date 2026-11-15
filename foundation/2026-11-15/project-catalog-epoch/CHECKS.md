# Actual checks

2026-11-15, Python 3.12.14. Rust/Cargo/rustfmt absent in PATH.

- GitHub main refs checked at start and end: unchanged, see REFS.json.
- All 16 `sources/` files' Git blob SHA-1 values equal the pinned Desktop tree.
- Python text generator reviewed independently first, then run as:
  `python3 -I -B -S regression/generate.py`. Exit 0, generated hashes in
  TEXT-CHECKS.json and selected function hashes in regression/extraction.json.
- `patch --batch --fuzz=0 -p1 -d apply-check < project-catalog-epoch.patch`:
  exit 0 against an owned baseline file copy.
- `cmp apply-check/src/ui/projects.rs candidate/src/ui/projects.rs`: exit 0.
- `git diff --no-index --check sources/src/ui/projects.rs candidate/src/ui/projects.rs`:
  exit 0, no whitespace issues.
- Diff numstat: +30/−2, one production file.

No project production code, Rust baseline/candidate tests, native UI,
backend/provider call, creation/deletion operation, build, installation or
upstream change was performed. The owned `apply-check/` tree is just a patch
application witness, not a running checkout.
