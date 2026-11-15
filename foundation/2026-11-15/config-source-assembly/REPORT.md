# Core config composition: validate, preserve sources, then prepare discovery

Status: an exact source-only composition of existing #86 Core, #137, #138 and #139 proposals. This is not a new finding, a new runtime reproduction, or full integration qualification. The combined patch adds no implementation changes beyond those four published inputs. No upstream checkout, live profile, server, provider, package installation or deployment was changed or run.

## Exact base and alternative

- Core main was freshly checked at `bcbda4435534a296c707a1daa250813d692f68e1`.
- Published inputs were retrieved from delivery commit `ee68d1574ee622f061eff8fb3283ba0a272aa9ae`.
- The plan is [PR155's bounded integration plan](https://github.com/Qweasd123tg/proteus-modules-dot/blob/ee68d1574ee622f061eff8fb3283ba0a272aa9ae/docs/integration-plan-2026-11-15.md). It already recorded a #139-before/after-the-fixed-#86/#137/#138-sequence check. This pass packages a combined alternative and additionally checks the full reverse order on fresh verified bytes. It does not present the previously established composition as a new defect or first proof.

The selected originals, all from that exact delivery commit:

| Input | Published path | Git blob |
|---|---|---|
| #86 Core | `foundation/2026-11-14/reviewed-simplification/core-config-validation.patch` | `0d8667e42243d02ef9d9ba371afe297ad57b448d` |
| #137 | `foundation/2026-11-15/provider-inheritance-preservation/provider-inheritance.patch` | `535425cb617ae53e03d4c571db5d93a13f0bd0c4` |
| #138 | `foundation/2026-11-15/instruction-source-bootstrap/instruction-bootstrap.patch` | `6dfd39d44a2dafdfd5aa06b75a5a243fc05699cb` |
| #139 | `proposals/mcp-schema-discovery-2026-11-15/mcp-input-schema-discovery.patch` | `45eaa80db06aa6ee6847681b6a22465c1e0ddce2` |

`composed-config.patch` is an ALTERNATIVE to applying these four originals on the unmodified pinned Core baseline. Do not apply it after the originals or add the originals after it. They are complementary boundaries, not prerequisites for one another; this bundle deliberately includes all four. Their internal helpers, callsites, test registrations and documentation remain together. A tree with a subset already applied requires a separately checked remaining-delta strategy, not forcing this bundle.

The #86 Modules history/compactor patch is not included or required for this Core-only slice. Desktop #134–136 are not prerequisites. No Cargo manifest, lockfile, public DTO, wire version, dependency pin or consumer selection is changed. The old #86 Modules pin `b5fac842…` must not be restored. Building or deploying a Core consumer from this source would require separate identity/pin verification; none was attempted.

## Coherent source invariants, not a single global transaction

1. **Shared typed semantics (#86).** Both disk loading and the edited Config Builder configuration call `validate_semantics`: selected provider, allowed module-config slots, hooks and prompt commands. The save call remains after requested edits and before assembly preparation/history/file publication. This deliberately does not revalidate resolved instruction entries as source-shaped data: the loader has legitimately retained both a file reference and its loaded text. Source instruction shape and asset resolution remain loader responsibilities. TOML representability and runtime preparation remain distinct checks.
2. **Source ownership (#137).** Existing TOML/JSON documents retain absent or explicit/partial provider definitions instead of receiving the effective inherited map. Active-provider selection is still managed. Directory overlays remain overlays. Missing ordinary standalone profiles still seed a complete initial config, including provider definitions. The two writer fixtures are still corrected to load their actual source; the directory fixture also removes workflow/module_config before its original managed edits. Their existing assertions are retained. No unrelated file-write mechanism is changed.
3. **Bootstrap source projection (#138).** Both missing-standalone writers use one cloned `initial_profile_source` that clears resolved text only for entries with file references. Inline text, reference spelling, kind, priority, order and providers remain. The JSON writer's subsequent managed-key updates do not reinsert instructions or providers, so the projection and provider-ownership rule survive composition. Existing source instructions and the missing reserved TOML directory overlay are not rewritten by this helper. Runtime configuration is not mutated.
4. **Discovery before registration (#139).** The existing input-schema validator runs on each final discovered `ToolSpec`; the whole conversion must succeed before registry insertion. Invalid schemas therefore reject the server's discovery batch without registering a valid prefix, while retaining the server-local diagnostic. A wholly valid batch still enters registry validation and can fail on collisions. For a batch mixing invalid schema and a potential collision, discovery rejection intentionally precedes collision checking. There is no catch-all around registration or general registry rollback. This has a deliberately different error policy from an invalid typed profile: an invalid-schema MCP server can remain configured with a local discovery error rather than fail the whole settings preparation.

These rules preserve different representations and failure boundaries rather than introducing one universal validator. No new framework or prepared-schema transfer API is added. The existing server-local discovery boundary and existing source/managed-field distinction carry the behavior.

## Scope, costs and remaining limitations

The combined production diff is +57/−59 lines across six files, net −2; the full patch is +755/−62 across 14 files, mostly existing proposal tests and documentation. This bookkeeping is not a performance result. The meaningful simplification is shared typed validation and removal of provider materialization, not this net line count. There is no additional LOC reduction from composition itself.

- #138 adds a full config clone on bootstrap; missing JSON also serializes the projected configuration in addition to its already serialized runtime value. Existing-profile saves do not call the helper.
- #139 compiles a valid input schema during discovery and again when the fresh registry cache is populated. No compiled-validator reuse, CPU, RSS, latency or allocation improvement is claimed.
- Bootstrap assumes a loader-resolved config recreated at its ordinary original standalone path. There is no provenance tag, relocation/rebasing, asset recovery, pre-write source reread or universal cold-load guarantee.
- Previously frozen explicit provider overrides are not repaired automatically. Lost include layout, fragment ownership and comments cannot be reconstructed from effective config. Broader managed-field inheritance is unchanged.
- Missing assets remain missing: bootstrap retains the file reference, and later load must still fail rather than silently substitute cached text.
- This is not a general all-or-none settings/registry transaction or a claim about external-edit races. Discovery/name-collision staging, valid-batch registration failures and existing publication mechanics keep their documented boundaries.

## What was actually checked

`SOURCES.json` records 34 verified blobs: 28 baseline Core source/document files plus four published patches, the #86 README and PR155 plan. The current Core tree was retrieved again; cached baseline bytes were rehashed to those exact Git blobs before copying. Published inputs were fetched again and Git-blob verified. Copies are intentionally source subsets, not complete buildable checkouts.

System `patch --batch --fuzz=0 -p1` dry-run and application succeeded for exactly two selected orders:

- #86 → #137 → #138 → #139.
- #139 → #138 → #137 → #86.

All 14 target files are byte-identical between those orders. No conflict, manual resolution, fuzz or semantic edit was needed; line offsets were accepted by the patch tool. This is target-file equality, not whole-directory equality because patch backup artifacts can differ. All 24 permutations were NOT checked.

The generated combined diff dry-runs and applies to another owned baseline copy, yielding those same 14 target hashes. Reverse application restores all 28 baseline files and removes the five newly added target files. `COMPOSITION.json`, `COMPOSED-TARGETS.json`, `DIFFSTAT.json` record these checks. These are text/file/hash checks, not Rust compilation or behavioral tests.

Python 3.12.14 `ast.parse` accepted the baseline and combined MCP fixture files. No fixture import, handler, subprocess, server or Python behavioral test was executed. Python otherwise performed file/hash/diff bookkeeping, not a substitute model of Rust semantics.

## Unrun qualification gates

The combined source contains 13 proposal-added Rust test functions: four #86 validation functions, three #137 provider functions, three #138 instruction-bootstrap functions and three #139 MCP discovery functions. All are retained, with each test module registered once. This is a source inventory, NOT 13 passing tests. The two #137 existing fixture edits are also retained. No new tests were added by this composition pass.

`rustc`, `cargo` and `rustfmt` are unavailable in the selected PATH. The combined tree was **NOT COMPILED; Rust tests and formatting were NOT RUN**. Historical #86 results on an older exact tree are not transferred, summed or reused as acceptance of this bundle. No app-server Save/reload, watcher, real MCP, external provider, full-suite or benchmark run occurred.

After a suitable toolchain is available, required qualification remains:

1. Format and compile the exact combined source, then run the focused Config Builder/config loader and MCP discovery suites, including the 13 retained cases and adjacent existing controls.
2. Preserve the loader's existing rejection of source entries containing both file and text, default/empty/first-save controls, JSON value handling and provider-selection errors.
3. Exercise actual Save/reload and cold-load boundaries for existing include/directory profiles and missing standalone profiles, keeping authored sources dynamic; missing assets must remain an explicit failure.
4. Exercise actual MCP invalid-schema cold assembly and settings-update paths with controlled fixtures, healthy siblings, empty/disabled servers, valid collisions and mixed invalid-schema/collision precedence. No external provider is needed for these proposed checks.
5. Verify the produced Core/consumer identity and applicable integration gates before any deployment claim. Passing only text application or isolated tests is insufficient.

Independent exact source review is recorded in `REVIEW.md`. Publication of this package would distribute a reviewed source alternative, not install or qualify a production change.

Combined patch SHA256: `1d9dea418830ad7459f3ec256e681fafa53d0886c7f08aee6f0f6c8fb3b07c8b`.
