# Tools/workspace integration audit, 2026-11-13

## Exact scope and versions

- Modules source: `3270dc0f894eaf4d0360306052b806099b8f5351` (clean source copy; only isolated diagnostic tests added).
- Modules' actual Cargo contracts/SDK dependency: Core `b5fac84245b075896c24763b3aebac79b4375c2e` (unchanged lock/dependency pin).
- Read-only cross-check of current Core source/prompts: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Audit copy: `/workspace/shared/tools-integration-audit`.
- Dynamic coverage: real direct-patch algorithm; actual file-tools ToolModule invocation for write/read/edit/find; actual installed ripgrep.
- No network services, no model provider requests, no sandbox/security policy changes, no publishing, no production implementation modifications.

## Confirmed P2: CRLF source cannot be updated by direct_patch; range-read → edit workflow also loses newline representation

Minimal original file: `old\r\nkeep\r\n`.

1. `write_file` creates it successfully; full `read_file` preserves the bytes.
2. `read_file(start_line=1, limit=2)` returns `old\nkeep`, with no CRLF metadata.
3. `edit_file(old_string=<exact returned text>, new_string="new\nkeep")` fails with `old_string not found in file content`.
4. A normal direct patch replacing `old` and retaining context `keep` also fails with `failed to match update hunk against current file content`.
5. Passing the entire patch with CRLF line endings still fails.
6. Identical LF source and patch succeeds; failed CRLF cases leave files unchanged.

Cause:
- `tool/direct-patch/src/lib.rs:59-64` removes line terminators/CR from patch lines.
- `tool/direct-patch/src/transaction.rs:278-296` retains CR when splitting source and compares exactly.
- `tool/file-tools/src/read.rs:240-244,274-278` normalizes ranges to LF while edit uses exact string matching.

The direct patch problem is independently actionable even if normalized ranged display is intentional: normal CRLF source lines are not representable in this patch format. Do not broaden this to all edits: a single-line edit not including its newline, or whole-file read/edit, can work. No data loss was observed.

Suggested fix direction: preserve/detect source EOL convention in direct_patch matcher/rendering without normalizing the whole file, and test CRLF/LF/mixed input separately. For file-tools, either preserve EOL for non-numbered exact ranges or expose actionable EOL metadata and document normalization.

## Confirmed P3: find_files applies result limit to newline pieces, not paths

On Unix, `write_file(path="first\nsecond.txt")` and direct `read_file` both succeed. `find_files(pattern="**/*.txt", max_results=1)` returns successful output `first`, which is not an existing file; following it with `read_file` fails. Without the limit, one actual file is reported as `match_count=2`.

Cause: `tool/file-tools/src/find.rs:111-125` invokes `rg --files` without NUL separation; `util.rs:50-64` splits and limits by newline. The output also has no machine-readable path array.

Suggested fix direction: use `rg --files -0`, parse/limit NUL-terminated paths, and provide exact paths in structured metadata or a JSON-visible output representation. Lower priority: requires an unusual legal filename.

## Evidence

- `baseline.log`: 17 direct-patch + 17 file-tools existing tests passed.
- `crlf.log`: both CRLF diagnostic tests passed by asserting the current incorrect behavior, with LF controls.
- `all-diagnostics.log`: 18 direct-patch + 19 file-tools tests passed (34 baseline + 3 diagnostic reproductions). A passing reproduction is NOT a product fix.
- `diagnostic-tests.patch`: only 66 added lines in test files.

Run:

```sh
source /workspace/shared/proteus-toolchain/env.sh
cd /workspace/shared/tools-integration-audit
CARGO_TARGET_DIR=/workspace/shared/tools-integration-evidence/target \
  python3 scripts/test.py -p direct-patch -p file-tools -- --nocapture
```

## Important rejected hypotheses and review boundaries

- Direct `*** End of File` removing final newline is documented in Core's `configs/prompts/direct-patch.md`; it is intentionally different from Codex anchoring and is NOT reported.
- Codex patch overwrite/self-move/nontransactional options are explicit upstream parity semantics; NOT reported again.
- rg's early closed pipe returned exit 1 in 20 actual trials, which existing wrappers accept; proposed max-results false-failure race was NOT confirmed.
- Reviewed source, without new dynamic findings: git-tools; code-mode bridge/engine/bootstrap; skill discovery; plan tool; shell output/session/capture paths; rg-search. This is not an assertion of complete coverage of those modules.
- Previously known concurrent edit lost update, split UTF-8 output, read_many invalid tail, stale LSP overlays, image dropping, callback cancellation/late result and other reported issues were not recounted as new.
