# Desktop settings composition: exact forms, ACK conflicts and accepted-profile epochs

Status: source-only assembly of existing #134, #135 and #136 proposals. No new production edits, UX policy, finding or tests were introduced. This is not compilation, native UI observation, HTTP integration, deployment or production qualification. No live profile or upstream repository was changed, and no actual catalog installation, application/MCP process or provider request was run.

## Exact base and selected alternatives

- Fresh Desktop main: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Actual Desktop contracts pin remains Core `41bdfffa6e70228278b4abc758b7f81a12672f35`, as recorded in the copied Cargo.toml. No Core source/dependency update is included.
- Published inputs: delivery commit `ed1450d15d4000bb8c5c4452db7cbe2ba49de2ba`.
- This follows [PR155's bounded integration plan](https://github.com/Qweasd123tg/proteus-modules-dot/blob/ed1450d15d4000bb8c5c4452db7cbe2ba49de2ba/docs/integration-plan-2026-11-15.md). Previous packages already recorded pair/group text composition; this pass checks all six orders and the final combined source.

| Selected input | Published path under `foundation/2026-11-15/` | Git blob |
|---|---|---|
| #134 | `mcp-json-form/mcp-json-prototype.patch` | `ff919ecc4a417acf1c3ed06e211c9e2ffcadf831` |
| #135 | `catalog-mcp-switch/catalog-mcp-switch.patch` | `bf0f99e4d5e703a165358b3a3417f5dc02c48cc3` |
| #136 | `settings-reload-save/settings-profile-revision.patch` | `ebd5c6dd4cfbfb984036c348fb2468d43352e107` |

These three selected patches have disjoint target-file sets and no ordering prerequisite between them. Their behavior still meets through SettingsView/Draft/ACK paths, so conflict-free text application alone is not a behavioral integration proof.

`composed-settings.patch` is an **alternative** to those three originals on unmodified Desktop 7eaf70c6. Do not apply it after them or reapply the originals afterward. A partly patched tree requires a separately checked remaining delta. No new hunk resolution or semantic edit was performed.

The earlier `research/proteus-continuous-audit-2026-11-13/evidence/desktop-settings/candidate-reloading-save-guard.patch` (blob `8c68c668998a1ed74cb60682e85bcc55b66a6e3d`) is explicitly excluded. It adds `!reloading` to Save eligibility; the selected #136 policy intentionally retains existing Save eligibility and rejects superseded read results instead. That historical guard was fetched only as an exact reference, not applied or silently combined. No schema, generic settings parser, receipt format or networking policy change is added beyond the selected proposals.

## 1. JSON forms preserve typed values, with an explicit UX migration

#134 renders Args as a JSON array of strings and Env as a JSON object of string values. The Env visitor sees decoded keys before collecting them, rejecting duplicates such as `"A"` and `"\u0041"`, non-string values, blank keys and trailing input. Args/Env replace their typed value only after complete successful parsing. There is no newline/KEY=VALUE fallback. EnvAllowlist and other ordinary line lists retain their existing parser.

This is the previously selected form-input contract, not a compatibility-neutral refactor:

- Existing typed profile values are displayed as JSON without changing stored vector/map schema. Args order, duplicate/empty arguments, whitespace and escaped line breaks remain representable. Env nonblank spaced keys/values are not trimmed; BTreeMap display ordering is not insertion-order preservation.
- Empty collections require `[]` / `{}`. Blank, `null`, old newline-separated arguments and KEY=VALUE input are invalid, retaining raw editor text and the last valid typed draft while blocking Save.
- Existing whitespace-only Env keys may be displayed but cannot be accepted when edited. This is not an inverse over every possible map and does not silently repair malformed source data.
- Already lost strings are not recovered. Older clients can reintroduce lossy edits; schema stability does not make mixed-client rollback safe. Migration of unsaved buffers across an application upgrade is not provided.
- Pretty JSON and escaping can be less convenient and use more display lines. Existing controls/preview/focus infrastructure remain; placeholders, README and DESIGN disclose the syntax. No new visual primitive or Zed-derived implementation was introduced by this assembly.

### Raw-edit junction with #136

The existing `mcp_text_changed` callback still invokes `update_draft` even when parsing fails or yields the same typed value. `update_draft` increments `edit_revision` unconditionally. Thus an invalid or same-value JSON edit is not invisible merely because the last-valid parsed draft is unchanged. The form retains its error/raw editor; Save remains error-gated. #136's successful-read guard uses that revision, not only parsed dirty state. This is verified source wiring, not an executed native invalid-JSON/reload scenario.

## 2. Receipt ownership is not ACK conflict equality

#135 uses `same_mcp_binding` at exactly three receipt checks. It clones the receipt, normalizes only `enabled`, and keeps derived equality for every other field. Exact Args/Env values from #134 therefore remain binding-significant. Non-switch edits and independent-name collisions still reject rather than being hidden by the comparator.

Before replacement, the existing binding's effective switch is captured and restored through the existing setter. Missing binding plus an explicit disabled-name entry preserves false; missing binding without that entry does not invent an enabled state and instead retains incoming default behavior. Existing bindings preserve their effective on/off state even when a new manifest changes its default. The stored receipt still records the manifest value.

**ACK rebase remains distinct and unchanged.** `CatalogChange::rebase` keeps complete before/current/accepted equality and the existing raw-editor guards. An overlapping newer enable can therefore be an explicit conflict, with the newer local draft retained, rather than an automatically merged switch. Unrelated changes can receive the accepted catalog delta. The new receipt comparator is not transplanted into reconciliation.

The catalog save path still reconciles, remaps retained editors, accepts the saved snapshot and then reports conflicts. This bundle does not claim that every concurrent switch or invalid raw form merges automatically, nor that real ACK ordering or receipt persistence was exercised. Only settings binding data was inspected in the catalog source; no installation or execution mechanisms were changed or investigated.

## 3. Accepted profile state has its own local epoch

#136 routes both accepted baseline/Ready assignments through `accept_baseline`, which advances `profile_revision`, including value-equal snapshots and both Save ACK branches. It does not increment `edit_revision` on acceptance or erase newer editors in the newer-edit ACK branch.

The catalog ACK path reaches the same acceptance method. It can therefore invalidate an older pending read without pretending the accepted catalog change was a new local text edit. The conflict feedback set after catalog acceptance is not replaced by a read from an earlier accepted-profile epoch.

Every admitted profile read, including initial loading, sets the existing `reloading` flag. The private `load` guard enforces one in-flight read. Its completion:

- ignores both success and failure after `profile_revision` changes;
- ignores a successful result after `edit_revision` changes or while the current draft is dirty;
- otherwise retains the existing success/error handling and clears the read flag.

Raw edits alone do not introduce a new error-discard policy: the edit-revision check applies to successful reads, while the accepted-profile check covers both outcomes. Save is not newly gated on `reloading`; its other validity/busy/error conditions still apply. No pending request is canceled.

This is a per-view local counter, not a server revision, ETag, remote timestamp or cross-window ordering guarantee. Rejection is conservative even if an older-dispatched result is value-equal or happens to reflect newer remote data; another explicit Reload can fetch it. History/addon streams and broader asynchronous-state questions are not assigned this counter by the bundle.

## Costs and evidence limits

The coherence comes from keeping three meanings separate: exact typed form values, catalog binding ownership versus concurrent edits, and local edits versus accepted snapshots. No generic async/settings framework was introduced.

#134 adds JSON formatting/parsing and its scoped Env visitor. #135 clones a receipt for each binding comparison, up to two checks per update or one per removal. #136 adds a local revision while centralizing duplicate acceptance assignments. None is a measured allocation, latency, RSS or overall LOC improvement. The full combined diff is +790/−73 lines across 15 files, primarily retained tests/documentation. Composition itself adds no new implementation reduction.

No new combined native scenario or runtime oracle was created. In particular, the source junction review does not prove the sequence “invalid JSON edit → catalog ACK → delayed Reload” in the actual UI or HTTP layer. No whole-settings race closure or process-launch compatibility is claimed.

## Checks actually performed

`SOURCES.json` records 34 verified blobs: 29 Desktop baseline/reference files plus three selected patches, the excluded historical guard and the plan. The Desktop Git tree was fetched again; cached baseline bytes were rehashed to that exact tree before copying. Published inputs were freshly fetched and blob-verified. Copies are source subsets, not complete buildable checkouts.

All six permutations of #134/#135/#136 passed system `patch --batch --fuzz=0 -p1` dry-run/application and produced identical bytes for all 15 targets. There was no conflict, manual resolution, force or fuzz. The disjoint target sets make the mechanics straightforward; they do not establish semantic independence. Target equality does not include patch backup artifacts.

The combined diff also dry-runs/applies to an owned baseline copy, matches all target hashes, and reverse-applies to restore all 29 baseline files and remove three new test files. `COMPOSITION.json`, target hashes, dependency metadata, source checks and logs preserve these file-level results. Python performed only file/hash/diff/source bookkeeping, not a model of Rust parsing or UI behavior.

## Unrun qualification

The combined source retains 24 proposal-added functions: #134 ten, #135 six and #136 eight. Two existing #134 connection tests retain their JSON-syntax migration. Each new test module is registered once. All tests are **NOT COMPILED / NOT RUN**; the #136 functions use the existing native-test context and controlled method completions, not executed HTTP or scheduler evidence. `TEST-INVENTORY.json` includes their fully qualified Rust test attributes.

`rustc`, `cargo` and `rustfmt` are unavailable in the selected PATH. No formatter, compiler, project scripts, native UI, HTTP/profile persistence, real catalog action, process or provider test was run. Historical results are not transferred to this tree. No dependencies were installed.

Later qualification would require the exact Desktop dependency/toolchain and separately authorized focused tests, then native form/Save/reset/error behavior and delayed GET/manual-ACK/catalog-ACK ordering with actual profile readback. JSON migration tradeoffs, late conflicting edits, current errors and conservative reload rejection must remain explicit during that validation. No such future execution is implied or performed by this source handoff.

Independent exact source review is recorded in `REVIEW.md`. Publication would distribute a reviewed source alternative, not a tested or installed production fix.

Combined patch SHA256: `8051d019d6d2371e20fd7c03589b9e6e3b2ee63433f4dd5a68d7dcc9a1d0e398`.
