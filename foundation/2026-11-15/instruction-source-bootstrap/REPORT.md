# Missing-profile bootstrap: retain instruction sources

Status: isolated source-only prototype for the existing PR85 `profile-recovery` finding #2. Not a new runtime reproduction, production change or complete profile-recovery solution. No real profile, upstream repository, model, server or watcher was changed or run.

## Applicability and source contract

Core main is `bcbda4435534a296c707a1daa250813d692f68e1`. The builder, persistence and loader files are byte-identical to their historical `89997df995df7c39b713e16aba216ecb19c8f497` versions used by the prior report. Delivery main after PR137 is `959c1540dbe555634d1225623aa4ecf8f66c2c6d`. The historical TOML server reproduction was NOT RERUN. JSON applicability is derived from its equivalent full-initialization branch, not a newly executed reproduction.

The configuration source requires exactly one of `InstructionSourceConfig.file` and `.text`. The loader first rejects conflicting input, then resolves a valid file reference by setting text while retaining file, kind, priority and order. This legitimate runtime representation is not valid source input.

For an existing profile, Config Builder loads the source before applying managed edits. If the path is absent, it intentionally uses its already loaded configuration. The missing-standalone writers currently serialize that resolved representation in full. Thus a valid file-backed entry becomes an invalid file+text source when the profile is recreated. The next cold load rejects it even though the runtime configuration used for Save was valid.

## One local projection, two bootstrap writers

The candidate adds a private `initial_profile_source` helper in persistence.rs. It clones the configuration and clears text only for entries with a file reference. Both full-bootstrap branches use it:

- Missing ordinary TOML profile: serialize the projected configuration instead of the runtime configuration.
- Missing JSON profile: initialize from the projected configuration instead of cloning the already serialized runtime value.

Inline text, file reference spelling, kind, priority and order are preserved. The original in-memory configuration remains resolved and is not mutated. No generic Serialize implementation, loader validation, contract DTO or public API is changed.

Existing TOML/JSON documents keep their authored instruction entries; their instructions are not rewritten. A missing reserved directory overlay still follows the minimal-overlay branch, rather than full bootstrap. No general managed-field persistence, provider policy, filesystem transaction, history or publication behavior is changed.

Production diff is +15/−2 lines, net +13. This is not a LOC reduction or performance optimization. The measurable structural change is that the two initial writers use one source projection rather than serializing an incompatible runtime form. It adds a full configuration clone on bootstrap; JSON also performs a second serialization on its missing-file path instead of cloning its previously serialized value. Existing-profile saves do not invoke this helper. No latency, allocation, RSS or frequency claim is made, and there is no new dependency or framework.

## Deliberate limits

- The supported provenance is a configuration loaded by the existing loader, recreated at its original standalone path. There is no provenance tag to distinguish loader-resolved file+text from an arbitrary manually constructed conflicting AppConfig. The helper is not a validator for arbitrary source data.
- Actual source files containing both file and text remain invalid. Neither loader rejection nor the existing corresponding test is modified.
- Relative references retain their meaning at the same location. Relocation/rebasing, restoring an absent directory tree and special reserved-overlay filenames are not added recovery contracts.
- Missing prompt assets are not recovered from cached text. Their file references are retained, so a later load still fails explicitly if an asset is absent. This proposal does not add pre-write source rereading or guarantee successful cold load for every missing-file Save.
- The vanished original document's comments, include layout and fragment ownership cannot be reconstructed from the effective runtime config. Full bootstrap remains full bootstrap, including effective provider seeding. Only the instruction file/text representation mismatch is corrected. This does not undo historical malformed profiles or recover their original source layout automatically.
- Existing TOML representability restrictions and JSON-specific values retain their prior handling. A separate source/runtime type split could provide stronger provenance, but is not introduced for this narrow boundary.

## Proposed regressions, NOT RUN

Three new tests call the actual persistence helper and AppConfig loader on synthetic temporary files. No model export, app-server or external service is started:

1. TOML/JSON mixed relative-file, inline and absolute-file instructions: actual load, ordinary existing-file Save control, removal of only the profile, bootstrap Save and actual reload. Compare source entries and resolved runtime entries, including order/kind/priority; check the original config is unchanged and the managed tools update survives. Later edits to both assets must be observed on load rather than frozen into inline text.
2. TOML/JSON missing-asset boundary: load while the asset exists, remove the profile and asset, then bootstrap. The saved source must retain the file reference without cached text; actual loading must still return the missing-instruction-file error. The in-memory cached text remains untouched.
3. First and repeated directory-overlay Saves: resolved instructions must not be materialized in the overlay, the ordinary fragment remains unchanged, asset edits remain visible and managed tools persist.

The unchanged loader test `load_fails_when_instruction_sets_text_and_file` remains a required negative control. Existing first-save/default/no-instruction and JSON value tests also remain applicable; PR137 supplies additional source-only first-save/provider controls when composed. These are qualification requirements, not transferred test results.

All three new tests and relevant existing tests were NOT RUN. Source-level plausibility does not prove compilation or behavior. This writer/loader test scope does not replace the historical full Save/server scenario.

## Mechanical checks and composition

Thirteen baseline source/document files were verified against the pinned Core Git blobs and SHA256. The exact published PR86 semantic-validation patch and PR137 provider-preservation patch were retrieved and blob-verified. They are separate concerns: semantic validation and provider ownership, respectively, not substitutes for source-form instruction bootstrap.

Strict git apply check, isolated application and exact-byte comparison against the candidate tree succeeded. All six application orders of this candidate plus those two exact patches succeeded and produced byte-identical combined files. No prerequisite implementation changes or force application were used.

An initial registration hunk near the top of tests.rs conflicted when PR86 had already added its registration. That unsuccessful text-check evidence and initial patch are retained as INITIAL-* artifacts. Moving only this candidate's module declaration between existing tests removed the context conflict; no test or production semantics changed. This is patch composition evidence, not compilation or runtime qualification. Historical PR86 executed-test counts do not apply to the combined current tree.

`rustc`, `cargo` and `rustfmt` are unavailable in the selected PATH. Rust tests, formatter, build, server Save/reload, HTTP, watcher, cold launch and packaging were NOT RUN. Python was used only for file/hash/diff bookkeeping, not a substitute implementation or behavioral oracle. No external provider calls or installations occurred.

Required next qualification: actual formatting and focused config-builder/config-loader tests, including the three regressions and existing malformed-source, first-save, provider and JSON controls; then the deleted-profile Save scenario through the server with applicable current fixtures, verifying subsequent reload and cold load. Broader recovery and missing-asset behavior must not be declared fixed by this prototype.

Patch SHA256: `1aec0214e04d770f339aefe8e0c143a51aeab19c42c3aa1bce2d48006a167722`. Independent architecture review is in INDEPENDENT-REVIEW.md; exact-patch review and mechanical evidence accompany the candidate. Publication of the package would distribute a proposal, not install or qualify a production fix.
