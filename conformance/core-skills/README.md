# Portable skills through actual pinned Core — runtime pending

This standalone probe closes a specific consumer gap: the portable skill module's
provider catalogue must feed its loader through **real Core process adapters and
`BoundTools`**, not merely a simulated wire host. It links unchanged Core/SDK
`3f36a003b4f3fde2242fc80f7aedac00dd127d1d` and uses the exact lint-corrected standalone portable module described below.
The eleven Core checks are authored but **not compiled or executed yet**.

## Assembly and authority

The same portable executable is configured twice: one component exports only
`context_provider/v4`, the other only `tool/v6`. This is a configuration assertion,
not a PID-count, isolation or shared-authority claim. Per-export configuration is
independent. The provider's entry carries `id`, digest and `path`; all three flow
to `portable_skill_load` (`catalog_path` is the load argument name).

The probe executable also has two **authored test-only exports**:

- `skills_probe.context` forwards one request through Core's allowed context
  callback to `portable.skills` and preserves the canonical chunks.
- `skills_probe.read_only` allows exactly the two portable tool names with
  `ReadOnly` safety, including canonical-name equality in evaluate. No skill
  metadata participates in this authority decision.

The harness constructs `AppConfig` directly, then uses `ModuleCatalog`,
`RuntimeRegistry`, the process context callback and `BoundTools`. It is not a TOML
profile/reference-pack integration, a complete agent turn or a model eval.
No Core files or production module code are modified.

## Eleven exact checks

`scenarios.json` is the ordered required list, not an optional test inventory.

1. Distinct configured single-export provider/tool components.
2. Provider catalogue to successful bound load; call ID, digest, path, body,
   untrusted-content warning and `allowed-tools: Bash(*)` retained **as data**.
3. Missing `catalog_path`: exact pinned validator diagnostic at schema `/required`,
   and Core's `validation_error` marker, after the matching positive load.
4. Changed body with unchanged valid ID/frontmatter/path rejects the old digest.
5. Catalogue refresh and successful new load in the same registry.
6. Removing the configured policy yields exact `deny_all` rejection despite hints.
7. Identical bytes under two existing roots reject the provider's different path;
   the tool's own catalogue then loads successfully in that same registry.
8. Global disabled ID reaches both provider and loader for a real previously
   loadable file; no nonexistent-target false proof.
9. Provider-only disabling does **not** revoke the independently configured tool.
   This is an explicit configuration-local limit, not a permissions-bypass claim.
10. A valid 100,000-byte body returns complete JSON below the module's 131,072-byte
    text cap and Core's default 200,000-byte output cap, with no truncation marker.
11. Sixteen valid files with 13,500-byte license fields produce the module's exact
    text-overflow error, not truncated JSON; reducing those fields permits the
    same registry to return all sixteen entries without warnings.

All module error paths check the original call ID and absence of truncation.
Digest and path binding are not immutable snapshots, trusted-content proofs or
TOCTOU prevention. The frozen module's trusted-root/symlink race limits remain.

## Running the standalone gate

From this package directory, point to the reviewed module package at standalone commit `592ad5cab6ab35fa181756a42607a32a696d9ccd`:

```sh
export PORTABLE_SKILLS_PACKAGE="/absolute/path/to/examples/portable-skill-catalog"
export CARGO_TARGET_DIR="$PWD/target"
bash ci/run.sh
```

`PROBE_RESULTS_DIR` may select a new output directory; it must not exist. The gate
verifies the pinned module hashes, fetches locked dependencies, records offline
metadata, checks formatting for both packages and builds only the two authored packages.
The probe is then run with cleared environment, empty HOME and a fresh workspace.
Nineteen authored `SKILL.md` files are deliberately created/changed and retained.
No foreign scripts, hooks, server implementation or upstream test suite runs.
Dependency fetching may use the network; the actual probe has no configured
model/network operation. This is not OS-level network isolation.

Runtime limits: 90 seconds, 2 MiB captured per output pipe, at least 1 GiB free
before launching. On timeout/overflow the controller group is killed and its
direct child receives a bounded five-second reap. **Core may own separate
component process groups; descendant settlement is not proven.** Every timeout or
capture failure fails the gate. No sources, caches or old evidence are deleted.

The gate requires all eleven exact ordered checks and matching completion markers,
no non-passing check, unchanged source/binary hashes and empty HOME. The verifier
has eleven separate Python synthetic controls; the bounded capture helper has
four tiny authored Python subprocess controls. These fifteen controls are not
Core cases and do not reproduce the Rust assertions independently.

`ci/check-core-skills.yml` is a proposed workflow for publication layout
`conformance/core-skills/` alongside `examples/portable-skill-catalog/`. It must
be copied unchanged to `.github/workflows/check-core-skills.yml` if authorized.
No remote branch/PR for this package has been created here.

## Standalone module provenance

The module input is publication commit `592ad5cab6ab35fa181756a42607a32a696d9ccd`,
not a silent rewrite of historical R5. Its only Rust changes from accepted R5 are
two guarded `.err().expect(...)` → `.expect_err(...)` lint fixes in `catalog.rs`
and `lib.rs`. Both success payloads implement Debug. The [standalone CI](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40249175569)
passed formatting, clippy with warnings denied, 29 behavior cases and one wire
case. Those results are **not this package’s actual-Core runtime results**. Exact
updated hashes and provenance are in `ci/portable-module.sha256` and `SOURCE_PINS.json`.

## Dependency maintenance and limits

Frozen portable code still uses `serde_yaml 0.9.34+deprecated` and transitive
`unsafe-libyaml 0.2.11`. The former is archived; the latter has the
[RUSTSEC-2024-0449 unmaintained advisory](https://rustsec.org/advisories/RUSTSEC-2024-0449.html).
This is a maintenance warning, not evidence of an exploitable bug in this probe.
No parser migration or complete dependency-security audit is claimed.

This does not test latest Core, Windows/macOS, full reference assembly,
in-flight cancellation/settlement, replay/journaling, OS sandboxing, real foreign
skill collections or hostile filesystem mutation. Lower host output budgets can
still truncate successful module output; only the pinned default is exercised.

See `VALIDATION.md` for run versus unrun status and `SOURCE_PINS.json` for exact
source identities. The useful next boundary after this gate is a separately
scoped official context-reader/full-turn integration, not weakening Core authority
or treating instruction hints as permissions.
