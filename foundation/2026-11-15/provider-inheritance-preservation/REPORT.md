# Provider definitions: preserve source ownership across Save

Status: source-only candidate for the existing PR85 `settings-lifecycle` provider-inheritance finding. Not a new reproduction or production-ready fix. No live profile, upstream repository, model, app-server or watcher was changed or run.

## Source applicability

Core main is `bcbda4435534a296c707a1daa250813d692f68e1`. Its persistence.rs is byte-identical to the historical `89997df995df7c39b713e16aba216ecb19c8f497` source underlying the prior report. Delivery main after PR136 is `de72c68da93787bcf097cfff4f6df8854058a792`. The prior TOML/include and directory runtime findings were not rerun; JSON applicability here is source-level, not a newly executed JSON reproduction.

The known problem is that an unrelated Save writes the entire effective provider map when the target document lacks a providers section. A provider inherited from a fragment becomes a local override. Subsequent edits to that fragment no longer change the loaded definition, even though the user did not edit provider definitions.

## Common invariant and minimal deletion

Provider definitions are not managed by SetConfigBuilderRequest. The request can select active_provider but cannot replace the providers map. For an existing profile path, the producer loads next_config through AppConfig::load before applying managed edits. Definitions therefore remain owned by their original explicit document, include or directory fragment.

The candidate removes the special materialization in both persistence formats:

- TOML: remove ProvidersToml and the block that fills absent providers from the effective config.
- JSON: remove the providers entry-or-insert branch.
- Remove the now-unused ProviderProfileConfig import from config_builder.rs. The relevant descendants were checked for use of that imported identifier; no unrelated implementation was changed.

This removes 18 production lines and one unused imported name, with no new helper, branch, dependency, DTO or schema. The improvement is a shared ownership rule across the two writers, not merely a shorter file. No latency, allocation or memory improvement is claimed; JSON still serializes the full effective config for its existing managed-field projection.

| Target | Preserved behavior |
|---|---|
| Existing TOML/JSON, providers absent | Leave the section absent; keep inherited definitions dynamic |
| Existing explicit/partial providers | Preserve exactly those local definitions; do not rewrite from the effective map |
| New directory overlay | Remain a managed overlay; do not seed provider definitions from fragments |
| Existing directory overlay | Keep absence or explicit definitions as authored |
| Missing ordinary standalone file | Keep the existing full-config initialization, including selected provider definitions |

The reserved directory-overlay filename remains excluded from standalone full initialization as before. TOML's missing-standalone branch already serializes the full AppConfig; JSON's NotFound branch already starts with the complete serialized next config. Neither bootstrap path is removed or replaced by a new fallback.

This is not a rewrite of all managed-field persistence. Selections, tools, module_config, addons, component deltas, history, atomic writing and publication keep their existing behavior. Only accidental ownership of provider definitions is removed.

## Existing fixtures and validity

Two existing low-level writer tests used AppConfig::default over an existing source that did not define providers. Rust Default chooses fake and supplies its definition, whereas deserializing missing active_provider/providers yields None/an empty map. Those fixtures therefore gave the writer an effective config that did not come from their source, unlike the production existing-profile producer. The removed materialization happened to repair that inconsistency.

The candidate adjusts only their setup:

- The directory-precedence test loads its source, then explicitly removes workflow and module_config before the same managed edits. All original assertions about precedence and removal remain.
- The existing symlink-preservation test loads its actual source before its original edit. Link setup, target selection, write mechanics and every assertion are unchanged. No symlink/security mechanism is modified or investigated by the patch.

This does not remove first-save coverage or assume defaults are absent universally. A new test explicitly writes a missing standalone TOML/JSON profile from AppConfig::default with a selected provider and checks the loaded definition. Existing server first-save tests remain unchanged. The private persistence helper is not being promoted into a generic operation that imports unrelated in-memory provider definitions into an existing profile.

## Proposed boundary checks, NOT RUN

The three new functions in tests/provider_inheritance.rs call the actual persistence helper and AppConfig::load on synthetic temporary files:

1. TOML and JSON include profiles, with absent providers and with an explicit partial local override. Check the saved source retains the same absence/override, include and unrelated runtime field; editing the fragment must affect inherited definitions but not an explicit override. The requested managed tools list must still persist.
2. First and repeated directory-overlay saves. Provider definitions stay out of the overlay, later fragment model values remain visible on load, and managed tools changes survive.
3. Missing standalone TOML and JSON files. Full initialization still writes and reloads the selected provider map.

These fixtures are validated by the actual loader in the proposed tests, not by a hand-written equivalent. They do not start the named synthetic model export, build a PreparedAssembly, call HTTP, or exercise hot reload. Source plausibility is not proof that the tests compile or pass. All three new tests and the two adjusted existing tests were NOT RUN.

The documentation change describes active_provider selection versus provider-definition ownership, the existing/new target distinction, and local override precedence. It does not promise automatic repair of already frozen profiles: a previously materialized explicit provider table is indistinguishable from an intentional override and is left alone.

## Verification, composition and limits

Thirteen baseline files are verified against their Core commit, Git blob identities and SHA256. Independent architecture review and exact-patch review found the ownership invariant and fixture corrections coherent. Strict git apply whitespace/check, isolated application and exact candidate-byte comparison were performed.

The previously published core-config-validation.patch is complementary: it addresses shared semantic validation, not inherited provider ownership. Its exact published blob was retrieved. Mechanical composition was checked on the current Core baseline in both orders. The first attempt exposed a file-start context conflict between the test module registrations. Moving only this candidate's registration to the bottom of tests.rs resolved that conflict; the original failed mechanical check is retained separately. Both final orders now apply cleanly and produce byte-identical source. No force application or semantic alteration of the published validation patch was used.

Composition does not transfer the historical validation patch's executed-test evidence to this candidate or to the current combined tree. PR134–136 concern separate Desktop changes and are not required for this Core proposal.

`rustc`, `cargo` and `rustfmt` are unavailable in the selected PATH. Compilation, formatter, targeted tests, app-server/HTTP save, watcher/live reload, module swap, doctor and packaging were NOT RUN. Python was used only for file/hash/diff bookkeeping; no Python TOML/JSON behavioral model substitutes for Rust validation. No external API or live provider was called.

Required qualification: run formatter and focused config-builder/config reader tests with the actual Core toolchain/dependencies, including both corrected fixtures and the new boundaries. Then exercise the existing server Save/include/directory scenarios and their cold-read/live-reload expectations with applicable fixtures before claiming runtime closure. Broader managed-field inheritance, external-edit races and automatic cleanup of old overrides remain outside scope.

Final patch SHA256: `0b6cf398a4eac76c45fb41ff91b7bc3bb372c3fe01d0d9326ddfcd25fb222352`. Evidence is recorded in SOURCES.json, READ-VERIFICATION.json, SOURCE-CHECKS.json, COMPOSITION-SOURCE.json, DIFFSTAT.json and the independent review files. This package remains an isolated proposal, not an installed or tested production change.
