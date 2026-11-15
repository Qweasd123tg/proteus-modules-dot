# MCP Args/Env: typed JSON form prototype

Status: reviewed source-only proposal, not compiled, not production-ready. This is a bounded treatment of the existing PR85 `mcp-text-roundtrip` family, not a new independently reproduced finding. No upstream, live profile, MCP process, or production installation was changed.

## Applicability and selected contract

- Desktop main was rechecked at `7eaf70c67dabba8595d98029c875ffc3f59209ad`; the affected model remains the previously reviewed lossy join/line-parser implementation. Modules main remains `c035142558f0fca43e9772fc0e50ca293abf1531`, delivery main `730527e8035d6114262712148e4e981cee241f2f`.
- The Desktop Cargo manifest actually pins contracts to Core `41bdfffa6e70228278b4abc758b7f81a12672f35`; this proposal does not upgrade it or substitute current Core main.
- The assignment explicitly selects a JSON array of strings for Args and a JSON object of string values for Env. Empty collections are `[]` / `{}`, not blank or `null`. Repeated decoded Env keys are rejected. There is no legacy lossy fallback.
- Existing `serde` / `serde_json` dependencies suffice. Cargo.toml, DTOs, generic settings parsing and EnvAllowlist behavior are unchanged.

The common invariant is that rendering and accepting an otherwise unchanged supported typed collection does not alter its decoded strings. Args ordering, duplicate arguments, empty strings, significant spaces, embedded line breaks, quotes, backslashes and Unicode remain representable. Env string values and nonblank keys remain exact; BTreeMap ordering is not a user insertion-order contract. Empty/whitespace-only Env keys remain invalid, so this is not an inverse over every mathematically possible map. Accepted strings are not thereby qualified for process launch.

## Minimal implementation

`src/settings/mcp.rs` replaces `args.join("\n")` / normalized `parse_lines` with pretty JSON formatting and `from_str::<Vec<String>>`. Env uses pretty JSON formatting and one local serde Visitor. The Visitor sees decoded entries before collecting them, so `"A"` and `"\u0041"` cannot silently collapse. It rejects non-string values and blank keys; `decoder.end()` rejects trailing input. Both assignments occur only after the complete parse succeeds, preserving the last-valid typed draft on any error.

The dedicated Env visitor is necessary because an intermediate `serde_json::Value` or ordinary BTreeMap deserialization would already discard duplicates. Reusing the generic `TextFormat::Json` would also admit the wrong shape and its existing blank/null semantics. No shared framework, alternate DTO, UI row identity, or second parser mode is introduced.

The same multiline native controls, event subscriptions, error retention, focus/index remapping, reset and save callbacks are retained. Only Args/Env placeholders and help text change. The existing source path records parse errors without replacing the raw editor text; settings `has_errors()` gates `can_save()`. This is source evidence, not an observed native UI test. README and DESIGN explicitly distinguish these exact JSON collections from ordinary normalized line lists.

Measured scope: eight changed paths, including two docs and test registration; model implementation is 303 → 314 lines, not a claimed code-size reduction. The benefit is removing one ambiguous representation boundary for the full Args/Env value family, not speed or a new abstraction. The new test module contains ten test functions; two existing connection tests are migrated to the selected syntax.

## Migration, UX and compatibility

1. Existing typed profile values are formatted directly as JSON when editors are constructed. The profile / AppAddonsUpdate representation remains the same vector and map. No stored-value migration, launch rewrite, or dual read format is added.
2. Old newline-separated argv and `KEY=VALUE` pasted into the form become invalid. Users must supply JSON string quoting/escaping. Clearing a field to blank now leaves an invalid editor until `[]` / `{}` is entered. JSON syntax is a deliberate form-input compatibility break, not a transparent UI cleanup.
3. Empty arguments and whitespace are now visible and intentionally retained. A nonblank key such as `" A "` is no longer trimmed into `"A"`; the two keys remain distinct. This normalization change is disclosed, not silently called equivalent behavior.
4. Already typed Env keys consisting only of whitespace can be displayed but cannot be accepted by the parser when that field is edited. The old parser also rejected such names. This proposal does not make all existing typed data valid or silently repair it.
5. Formatting does not recover strings previously destroyed by a lossy edit. An older Desktop client still using the old parser can reintroduce the problem when editing exact values. Rollback and mixed-client editing are not automatically safe merely because the profile schema is unchanged.
6. Existing preview/expansion and textarea surfaces are retained. Pretty JSON may consume more display lines, and escape syntax is less convenient than one item per line. Placeholder/help/README document the change, but discoverability, raw invalid-buffer retention, cursor/focus and save/reset experience still require native acceptance checks. No claim is made about migrating unsaved raw buffers across a running application upgrade.

AGENTS-required Zed source was inspected at `e2f00a41ac6789f0ae52b229567ad5715266e400`, `crates/settings_ui/src/pages/mcp_servers_page.rs` (blob `92cee7ff3a4a7b84ae6c5d52f5440ddde2435b8b`). Its Args join/split is itself unsuitable as a lossless codec; its native layout is a reference, not the correctness contract. The assignment chooses the JSON syntax divergence. No Zed implementation was copied, and no new visual primitive or dependency is needed. DESIGN's generic list wording is clarified rather than treated as requiring lossy Args input.

## Evidence and verification limits

`SOURCES.json` and `READ-VERIFICATION.json` pin 17 baseline files by commit, Git blob identity and SHA256. `DIFFSTAT.json` pins the changed-file outputs. `SOURCE-CHECKS.json` records actual strict `git apply --check --whitespace=error` and application in `apply-check-v2/`; all candidate file bytes matched the applied staging copy. These operations check patch mechanics, not Rust behavior.

`rustc`, `cargo`, and `rustfmt` were unavailable in the selected PATH. Compilation, formatter, Rust tests, native UI, HTTP save/profile readback and actual MCP process execution were NOT RUN. Python was used only for file/hash/diff bookkeeping; no Python parser model is substituted for Rust tests. The earlier historical report's runtime observations are not rerun or upgraded by this proposal.

The ten proposed tests cover rich existing values/clean dirty-state, neighboring Args and Env edits with undo, explicit empty collections through the existing change projection, malformed/wrong-type/trailing inputs with unchanged drafts, decoded duplicate keys, nonblank spaced keys, unrelated-field edits and the existing save DTO's JSON serialization. These tests are compile-plausible after independent review, not ten passing tests. The DTO test does not exercise an HTTP save, persistence, acknowledgement or a subprocess.

Required before production qualification: run formatter and focused settings tests with the actual Desktop dependency/toolchain; run native invalid JSON → correction, blank → explicit empty, undo/reset, focus/reorder/removal and save-ack checks; verify actual profile save/readback preserves the typed values. Any historical process-level closure needs a separately authorized applicable check. Existing unrelated save/lifecycle constraints are not declared fixed.

Final patch SHA256: `d53bbf0d84002cb6c986cbbcb12d792c1bdd892351f6b67a712c624c8320f66a`. `SOURCE-REVIEW.md` records independent review; its initial seven-path review is followed by the final documentation/17-source addendum. This package is a proposal suitable for review, not evidence of production readiness or a new benchmark.
