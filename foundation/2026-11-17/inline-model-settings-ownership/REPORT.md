# Core: source ownership of partial inline model settings

## Scope and new finding

Core base: `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`.
Initial delivery deduplication: `fd8f893314f22ce591921293cb7384cc6f1737c1`, through #174.
Publication refresh: Core main remains the same; delivery main is
`cab9b129dbea45cbffd7b424e3bafe2908805ba4`, through #176.
[#175](https://github.com/Qweasd123tg/proteus-modules-dot/pull/175) newly qualifies
the separate #167/#171 repairs; #176 covers a Modules ContextChunk projection.
Neither duplicates this inline persistence correction.

The latest named-model/inline-role path inherits missing provider entries in
`module_config.model` from its parent. An inline child may explicitly own one
provider's settings while inheriting another provider's settings.

On an unrelated Config Builder save, the writer previously preserved inheritance
only if the child had **no** model-settings table. With a partial local table it
serialized the entire effective map, silently giving the child ownership of
parent entries too. A later change of those parent entries was then hidden by the
newly materialized child override.

Sources: [inherit missing model settings](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/crates/proteus-core/src/core/config/models.rs#L322-L338),
[TOML persistence](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/crates/proteus-core/src/app_server/config_builder/persistence.rs#L163-L183),
[JSON persistence and old omission predicate](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/crates/proteus-core/src/app_server/config_builder/persistence.rs#L305-L374).

The real Rust reader/writer regression confirms this in **both TOML and JSON**:

- child owns `fake.implementation = child-local`;
- parent owns `other.marker = parent-before`;
- saving only a changed child tools list also writes `other` into the child;
- after editing the parent's marker to `parent-after`, the child still reads
  `parent-before`.

This uses `AppConfig::load`, the actual `persist_config_builder` helper and reload
on temporary files. It is not a Python emulation and does not launch a model,
process fixture, app-server, watcher or UI.

## Bounded correction

If the inline child's effective model settings have not changed, preserve its
original local model-settings table, including a partial table, empty table or
absence. Both format writers use the same equality decision. They no longer
confuse unchanged effective settings with locally authored settings.

Intentional changes to the effective model-settings map, non-inline profiles,
missing-source behavior and the existing handling of all other managed fields
remain on their previous paths. No schema/API/provider-specific behavior was
added. Production delta is +6 lines, not a claimed speed or RAM optimization.

Existing materialized overrides are not automatically removed: they cannot be
distinguished from deliberate local settings. The known external-edit race and
include deletion/roundtrip problem remain separate.

## Deduplication

- #137 corrected provider **definitions** and explicitly excluded module_config.
- #167 corrects file-include model-choice spelling, not partial inline settings.
- #171 corrects local alias scope, not persistence source ownership.
- The old state-install finding concerns deletion returning from ordinary file
  includes, rather than an unrelated inline-child save freezing future updates.
- Recent upstream `30f1013`/`cdf4aa5` introduced the inline/named-model path under
  inspection; #174 only reconciled adoption of the older #87–89 chain.

No process/security lane was investigated or executed.

## Native verification

Rust 1.95.0, locked dependencies, offline, one build job. No scripts/test.py,
reference fixture build, process invocation, provider request or remote mutation.

- Baseline original test: compiled; failed on TOML capture as expected.
- Final regression collects both formats: compiled; failed with four diagnostics,
  one capture and one blocked-parent-update diagnostic per format.
- Standalone candidate: **5 model_names tests pass** (four existing plus the new
  regression), then **5 inline_roles tests pass**. Ten distinct tests, not ten
  new tests. All use parser/writer/temporary-file boundaries.
- Changed-file rustfmt check and git diff --check pass.
- Existing dead-code warnings from profile_watch controlled helpers remain.
- Full workspace, actual app-server Save/publication, watcher, process, HTTP,
  native UI, packaged binary, hosted CI and performance checks were not run.

Logs are in `logs/`: baseline-native.log, baseline-both-formats-native.log,
candidate-model-names-native.log, candidate-inline-roles-native.log. Absolute
workspace roots are replaced with `<CORE_CHECKOUT>` or `<COMPOSED_CORE_CHECKOUT>`;
test names, outcomes and diagnostics are unchanged.

## Composition

Original standalone patch application with #167 conflicts in both orders because
its JSON call-site context was expanded by #167. These expected mechanical
failures are retained in COMPOSITION.json; no forced/fuzzy apply was used.

An explicit `inline-settings-on-PR167-PR171.patch` variant targets the exact raw
#167 production patch + #167 regression patch + #171 patch. It retains both
existing corrections, adds the same source-ownership correction and regression,
and formats two preexisting long lines in the #167 material. Strict forward
application and reverse application reproduce all expected file bytes exactly
(VARIANT-CHECKS.json). The standalone and composed variants are alternatives,
not patches to apply together.

The composed native regression **passes** (one test, both formats), recorded in
`logs/composed-regression-native.log`. This rerun checks the new invariant on the composed
source; it does not rerun the full #167/#171 suite and is not an eleventh distinct
test in addition to the ten standalone tests.

Delivery publication does not apply this candidate upstream, install it or
deploy it. The exact patches and evidence receive a separate read-only review
in INDEPENDENT-REVIEW.md before publication.
