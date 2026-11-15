# Direct list_dir: preserve enumeration error

## Result

One bounded functional source audit identified a direct-tool error-projection
candidate: a late directory-enumeration error is silently removed by
`entries.flatten()`, and the remaining names are returned as a successful
`list_dir` result. Suggested priority **P3**, not an architectural redesign.
The candidate uses the existing tool error path instead. Independent review
found no issue in the final one-file patch.

**Source-only proposal. Not compiled, not rustfmt-checked, not runtime-reproduced
or regression-tested. Upstream source is unchanged. Delivery publication does
not integrate or qualify the change upstream.**

## Sources and deduplication

- Modules `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Delivery `f4af7dc3071903ee6efddbc9ed1a2ba1ddfc312f`, containing PR162 plus the
  later merges of old PR62/67/73/74/77/80.
- `tool/file-tools/src/list.rs` blob
  `18ed63f2989e3e607d2767b74a02390632dd4725`.
- SOURCES.json records four exact source/doc blob hashes checked locally.
- Read the delivery integration plan and the relevant PR85 initial-modules and
  tools-integration reports, PR145 report, current source and existing tests.
  A follow-up duplicate scan covered 78 prior package README/REPORT texts and
  12 selected PR85 file/UI/tool reports; no direct list_dir iterator-error
  duplicate was found. This is not an exhaustive novelty check of every PR85
  artifact or older audit.

This is a different path from PR145's Files-panel cache/expansion semantics.
It follows the same error-family principle, but does not extend that patch,
fix its open root-cache limitation, or claim a second independent runtime
incident. Known #119/#124 UTF-8/CRLF and PR85 newline-delimited find_files were
not republished. The per-file formatted byte budget was not promoted: its
contract is ambiguous and existing tests intentionally enforce a shared budget.

## Source argument

The standard library explicitly permits `read_dir` to yield an error after
successfully creating the iterator:
[Rust read_dir documentation](https://doc.rust-lang.org/std/fs/fn.read_dir.html)

Baseline `list.rs` handles only opening the iterator at lines 83–92.
At line 96 `flatten()` converts each `Result<DirEntry>` into zero or one item,
therefore discarding `Err`. Lines 109–114 publish the remaining entries without
an incompleteness marker. For the abstract iterator sequence
`Ok(A), Err(E), Ok(B)`, baseline source necessarily publishes A and B as success.
This is a source-level counterexample, **not a synthetic or OS test run**.

The one-file patch is +14/−1 source lines. It uses `for entry in entries` and an
explicit `match`, returning the
existing `err_result` on the first observed enumeration error. It adds no retry,
collector, extra list, new protocol field, cache, error classifier or dependency.
The ordinary successful path is unchanged: sorting, name formatting, count,
metadata, and `file_type` failure represented as `unknown`. That last case is
not suppressed enumeration: the entry's name is already known.

This deliberately changes the error case from partial success to explicit
failure. It is not a strictly behavior-preserving refactor. A successful read
still is not an atomic filesystem snapshot, and concurrent directory changes
are not newly detected or prevented. Error frequency and OS-specific trigger
conditions were not measured. No performance benefit is claimed.

## Verification actually performed

- Exact Git blob hashes checked for the saved sources.
- Patch `git apply --check` succeeded on the exact pinned list.rs.
- Applying the patch produced byte-identical candidate source; reversing it
  reproduced the original bytes.
- `git diff --no-index --check` emitted no whitespace diagnostics.
- Independent read-only review of both the finding and final patch.
- Final patch SHA256:
  `2b9d50f8290499c36ecf90f21c6ba58b9745b84bc777cfb310978f3931ea652f`.

Python was used only to materialize/check bytes and generate the unified diff.
No project code, scripts, Rust, provider calls, process/security/cancellation
investigation, or live user data were involved. All final source copies match their expected Git blob hashes.

## Before upstream integration

Rust/Cargo/rustfmt are unavailable in this environment. With the pinned toolchain,
run the existing focused `python3 scripts/test.py -p file-tools` gate and check
formatting. That healthy-directory test alone does not cover iterator errors.
A deterministic iterator-error seam or real OS fault fixture would be needed
to regression-test failure before/after successful entries. Do not add a
production collector framework merely to manufacture a passing test, and do
not claim runtime verification without exercising the final tool path.

No test sources or passing test counts were invented. The existing test
`list_dir_returns_sorted_entries_with_kind` remains unchanged and was not run.
Publication of this candidate is delivery documentation, not upstream
integration or release qualification.
