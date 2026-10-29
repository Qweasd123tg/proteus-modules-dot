# Restricted-profile command fixture repair — source-only

## Status

**Rust test: NOT_RUN. Compilation: NOT_RUN. Product execution: NOT_RUN.
GitHub Actions: NOT_RUN.**

This is a small, unapplied source patch and offline evidence bundle. It is not a
compiled or runtime-qualified fix. Static checks below validate source bytes and
test structure only; they cannot establish that Rust compiles or that the test
passes. No production worker, installer, Core build, or repository script was run
to prepare this bundle. No workflow is included.

## Pinned inputs

- Core: `Proteus-harness/Proteus-core@125a9eb4088991513e9f61d899469be2076e266c`.
- Corrected file: `crates/proteus-core/tests/config_profiles.rs`.
- Preimage Git blob: `1b7cb442583e0b9ccb3df7152508857bc6dbb9d6`.
- Restricted fragment blob: `428603e5ff9728c2518fd3832975b5a43fad5fa7`.
- Modules inventory: `Proteus-harness/Proteus-modules@5fa8978684a37e8083c64f4d6cf0289e72450c6a`.

All source inputs were read through the GitHub connector at these immutable
commits. `module-inventory.json` retains the five relevant Cargo manifests and
export manifests, with original Git blob identities. `manifest.json` records
SHA-256 and Git blob hashes for every other bundle file.

## Defect and scope

The shipped restricted profile now uses independent executable names, but the
Linux-only launch-description test still copied and asserted the old aggregate
name `proteus-reference-module`.

`fix.patch` changes only that test. Its six explicit expectations are:

| Component | Expected executable | Export |
|---|---|---|
| reference-workflow | proteus-coding-workflow-module | workflow/coding.codex_loop |
| reference-context | proteus-context-pack-module | context/codex_context |
| reference-policy | proteus-policy-pack-module | policy/codex_policy |
| reference-compact | proteus-codex-context-preparation-module | hook/codex_compact |
| reference-search-tool | proteus-rg-search-module | tool/rg_search |
| reference-search-provider | proteus-rg-search-module | context_provider/rg_search |

The fixture copies the current test executable once into its private `bin`
directory, then creates same-directory hard links for the remaining distinct
names. There are five names, not six binary copies. These fixture files are used
only by launch validation; this test does not execute them. There are no symlinks,
installed-worker dependencies, or changes to the test process environment.

All original assertions for the six restricted components, exact single exports,
empty configured environment, child PATH, empty arguments, cwd, read-executable,
read-only grants, no writable grants, and no network remain intact. Both command
assertions compare against explicit expected strings, not whatever the profile
happens to contain. All bytes outside this test are unchanged.

The runner's unnecessary package preparation and the aggregate-based runtime
smoke remain separate issues; this patch deliberately does not change them.

## Offline verification

Requires Python 3.11 or newer; uses only the standard library and local text.
Run from this bundle directory:

```sh
python3 -B verify_static.py
python3 -B test_verify_static.py
```

The verifier checks exact source/patch hashes and pins, all six mapping values,
the five distinct fixture names, pinned fragment policy, module manifest/export
mapping, exact patch reconstruction, preserved assertion text, unchanged external
text, and the single-copy/hard-link fixture form. The ten verifier tests include
negative cases for arbitrary commands, omitted bindings, weakened assertions,
repeated copying, changed network grants, unrelated edits, corrupted patches, and
missing exports. These are tests of the verifier, **not Rust or Proteus tests**.

An independent source review accepted the patch. Before packaging,
`git apply --check --whitespace=error-all` succeeded against the exact pinned
preimage. This does not imply compilation, formatting, or runtime qualification.

## Applying later

`preimage.rs` and `postimage.rs` are complete before/after snapshots;
`fix.patch` uses the original repository-relative path. On an independently
verified compatible Core checkout, first run:

```sh
git apply --check /path/to/fix.patch
```

Applying the patch and running Rust checks require a separate authorized execution
step with adequate disk capacity. Do not describe this bundle as a passing Core
test result, a full gate, an upstream fix, or a released binary.
