# Catalog MCP: distinguish binding equality from the user's switch

Status: source-only candidate for the existing PR85 `catalog-mcp-toggle` P2 family. Not a new finding, not compiled, not runtime-qualified, and not a production fix. No live profile, process, installation or upstream source was changed.

## Applicability and invariant

Desktop main was rechecked at `7eaf70c67dabba8595d98029c875ffc3f59209ad`; `src/catalog/install.rs` is byte-identical to the historical `75bf201764278eac4b50d156650edcf1429101ff` source underlying the existing report. Delivery main is `69895e77d77993961f61dd47a5da895d528b7b72` after PR134. The historical runtime reproduction was not rerun here. The source confirms the same sequence: a manifest with enabled=false is installed; the ordinary UI switch calls Draft::set_mcp(true), which sets the entry's enabled=true; receipt equality then rejects update/removal as a manual binding edit.

Two different relations are currently conflated:

- A catalog receipt identifies an exact installation binding, excluding the user-controlled on/off switch.
- Reconciliation compares complete before/current/accepted state to avoid losing edits while a save is pending.

The candidate makes only the first relation explicit and reuses it at all three receipt checks. It does not replace complete equality in the rebase algorithm.

The update invariant is to retain the effective on/off state of an existing binding, whether that state came from the entry's enabled flag, disabled_mcp_servers, or the ordinary UI switch. New entries still use the manifest default subject to existing disabled-name entries. An absent old binding is not an implicit request to enable a new manifest.

## Minimal source change

`same_mcp_binding(current, receipt)` clones the receipt, normalizes only its enabled field to current.enabled, and uses the existing derived equality. Every other current/future field remains part of the comparison without a hand-maintained field list. The helper replaces the two update/name-collision comparisons and the removal comparison. Non-switch edits still reject before mutation; the independent-server name check is not removed.

Before removing/replacing the old entry, connect captures an optional effective switch:

| Previous state | Captured value | Result after replacement |
|---|---|---|
| Existing binding | Some(current effective on/off) | Apply through existing Draft::set_mcp |
| Missing binding, disabled old-name entry | Some(false) | Preserve the old tombstone-only behavior |
| Missing binding, no disabled old-name entry | None | Do not override the incoming manifest/default |
| No previous receipt | None | Retain fresh-install behavior |

This is deliberately symmetric for existing on/off state. Ignoring enabled in equality alone would still allow a new enabled=false manifest to turn an existing enabled server off. Conversely, blindly copying mcp_enabled(old) would force enable from a stale receipt because mcp_enabled returns true for an absent, non-disabled name. Both errors are addressed by the same local transition, not by a new settings framework.

Scope: three changed paths, 286 → 301 implementation lines (+15 net), one test-module declaration, and six proposed test functions. No dependency, DTO/profile schema, native control, receipt format or Core change. The helper clones a config for each comparison (up to two receipt checks per update, one per removal); no speed, allocation reduction or overall LOC reduction is claimed.

## Integration boundaries and tradeoffs

- Existing bindings retain their current effective switch even if the new catalog manifest changes its enabled default. That is the intentional user-state-preservation contract, extending the current off-state preservation to on-state as well. It does not mean catalog defaults never matter: new/absent bindings retain the existing default/tombstone rules.
- The stored receipt remains the catalog's manifest value. Updating the receipt from every ordinary UI toggle would couple separate save/prefs lifecycles; this candidate avoids that coupling. Repeated updates/removal use the same explicit relation instead.
- Catalog changes are prepared against the saved baseline; the receipt is recorded only after an accepted save (or the existing no-change path). The proposal does not alter this lifecycle. Native ACK/receipt persistence has not been exercised here.
- Current CatalogChange::rebase is intentionally unchanged. Unrelated newer edits can receive the accepted catalog delta. An overlapping late enable can change enabled itself; complete equality then reports an explicit conflict and preserves the newer draft. The candidate does not promise automatic merging of every concurrent switch, and does not weaken the raw-editor conflict guards to create that promise.
- Replacing all apparent equality duplication with the new helper would be wrong: receipt ownership equality and concurrent edit detection have different contracts. The helper is local to the three receipt checks.
- PR134's JSON form proposal changes a separate textual boundary. Exact Args/Env values still participate in receipt equality. Both patches apply in either order with byte-identical final source, but that is only a patch-mechanics composition check, not a compiled integration test.
- Existing duplicate-name/malformed-profile constraints, remote-save failures, unrelated reload races, filesystem installation paths and process/runtime semantics are outside this patch. No security or launch behavior is investigated or claimed fixed.

## Proposed checks, not results

The new `src/catalog/tests/mcp_switch.rs` is registered in the existing catalog tests module. Its six test functions use synthetic in-memory Installed and Draft values without files, provider calls or subprocesses:

1. A matrix of old/new manifest defaults, same/renamed binding, and ordinary set_mcp sequences, checking effective state, exact non-switch parameters, neighbor preservation and subsequent removal.
2. Fresh/stale receipts with absent bindings, changed defaults and old/new name tombstones, retaining the current absence behavior.
3. Repeated updates after enabling an initially disabled manifest, when each new receipt still contains the manifest default.
4. Non-switch edits (command, Args, Env, cwd, numeric/protocol fields) and independent-name collisions reject with an unchanged draft.
5. The actual existing CatalogChange::rebase method accepts the prepared catalog delta while retaining an unrelated later edit, for same-name and renamed updates.
6. The same existing rebase method keeps a late overlapping enable as an explicit conflict, preserving the local draft rather than silently replacing it.

These are proposed Rust tests, NOT RUN. The source-level review finds the expectations consistent with current methods; that is not proof of compilation or behavior. In particular, rebase tests are model-layer transitions, not native save callbacks, real HTTP persistence, UI clicks or receipt writes.

## Verification and remaining gates

Fifteen baseline files are pinned by commit, Git blob identity and SHA256 in SOURCES.json / READ-VERIFICATION.json. Strict `git apply --check --whitespace=error`, application and exact candidate-byte comparison were performed in an isolated staging copy. The PR134 composition check applied both exact patches in both orders and compared the final bytes. SOURCE-CHECKS.json records these mechanical checks and the exact PR134 patch hash.

`rustc`, `cargo` and `rustfmt` were unavailable in the selected PATH. Rust compilation, formatter, all six proposed tests, native UI/ACK, real HTTP/profile persistence and MCP execution were NOT RUN. Python was used only for file/hash/diff bookkeeping, with no behavioral substitute for Rust. Historical test counts are not carried forward as new validation.

Before production qualification: run focused catalog/settings tests with the actual pinned Desktop contracts/toolchain; exercise install-disabled → UI enable → Save → update/remove, same-name and renamed updates, save failure/retry, absent-receipt/default controls and delayed-ACK conflicts through applicable native/HTTP gates. Any broader concurrent-switch merge requires a separate explicit contract rather than transplanting this comparator.

Patch SHA256: `a860373f8c8b0488c77a02ed22d2fac5d45fe027f555a835de30c650e5f986dd`. Independent review is in SOURCE-REVIEW.md; the earlier options review is INDEPENDENT-REVIEW.md. This package proposes one bounded family-level invariant, not closure of all MCP/catalog lifecycle findings.
