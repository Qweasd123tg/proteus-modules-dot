# Independent review: opt-in conformance CLI dependency

No source-semantic blocker found in patch
`21d7c31555962744b8173bcf6aaaadf0732a4a4885d9ce37e74f56bdbf74b2ef`,
against Core `befd30516aefa6f0a0ad5db9924ad4957160b8dc`.

Final acceptance: full-file strict forward/reverse git apply with
--whitespace=error-all independently passed, with exact candidate comparison
and baseline restoration. Added/removed source lines match the earlier reviewed
proposal; the final artifact corrects its patch context without changing behavior.
This is static applicability, not execution evidence.

The public patch normalizes only the new-file diff header's old-path staging
prefix from author artifact `444eda55cc39340de2ee126ff8143a54e9a3cb9e00413a2da00a6c05ef714d1b`.
Applied source bytes are identical; the full strict roundtrip was repeated after
that header-only normalization. No production or test source was edited.

## Reviewed boundaries

- Optional clap is enabled only through `conformance-cli = ["dep:clap"]`.
  Explicit required-features belongs to the existing same-name/same-path binary;
  no duplicate executable, renamed contract or second implementation is added.
- No protocol library/runtime code changes. SDK depends on the protocol without
  feature activation. Core independently depends on clap for its own CLI; this
  change must not be advertised as removing clap from Core or every worker.
- `scripts/test.py full` adds the namespaced feature before forwarded options,
  so its existing workspace Cargo test gate still selects the conformance
  binary and its three parser/environment unit tests. A narrower protocol-only
  test invocation intentionally no longer includes that binary by default;
  documentation supplies the explicit feature invocation.
- Manual workflow retains the full runner and existing Rust starter smoke gate.
  Its explicit conformance build now enables the feature. New Python regression
  source is wired into that same manual workflow; workflow triggering unchanged.
- CLI source is unchanged: strict export decoding, parser requirements, timeout
  and paired-probe validation, and terminal failure conversion remain intact.
  Selecting its binary without its required feature is now an explicit Cargo
  selection error, not a fallback or silently different executable.
- Existing architecture and all five example conformance command lines in this
  patch supply the feature. No consumer Core pin or lockfile version is invented.

## Regression-source safety and meaning

The new unittest discovery step imports scripts/test.py using the scripts search
directory. Its imports build_module and sources only define functions/constants;
resolve/build subprocesses are not called by module import. The tests patch
test_env, both fixture preparation functions, and subprocess.call before invoking
runner.main. They assert full command shape, fixture counts, library-default and
explicit CLI feature pass-through. None of these tests was run in this review.

These assertions check runner selection, not successful Cargo resolution/build,
CLI behavior or the absence of clap from a realized worker graph. Existing CLI
unit tests and smoke fixture remain the proper executable evidence for those
boundaries once execution is authorized.

## Manifest/lock implications

Workspace resolver remains version 2. The dependency version/features are
unchanged; only activation is gated. The existing lock can retain clap, including
for Core's independent direct edge and optional resolution. Do not prune it by
text or claim --locked success without an authorized resolver check. Workspace
feature unification means a full gate intentionally enables clap for the protocol;
the size/dependency benefit must be checked on the selected normal worker graph,
not inferred from workspace tests. No runtime or numerical savings are claimed.

## Independent source identities read through the connector

| Path | Git blob |
| --- | --- |
| scripts/test.py | cfb44c0f3db0491de42c4165627374281d3a647c |
| scripts/build_module.py | 4140861600e961c83898fb067faacc3d6de16006 |
| scripts/sources.py | 13dfc29a51df144be9a1681495ec89ea46defe19 |
| .github/workflows/check.yml | b7e46d8418e75a2b8e8e27c557d7a947f54b1e68 |
| Cargo.toml | 14b19f586779a418059d25d26e10bd90f37279c2 |
| crates/proteus-module-protocol/Cargo.toml | d0c747f589a384fe3b9bb259f1edb972e7c76233 |
| crates/proteus-module-sdk/Cargo.toml | 03049779bb6eefaca5f3dba2158ff629ae0a6aca |
| crates/proteus-core/Cargo.toml | 439602fb164bc64a0bc3aba11a715f5f460970e4 |
| crates/proteus-module-protocol/src/bin/proteus-component-conformance.rs | 6b6302792ee214025a2a26419da4711fd2320862 |

Author's broader 118-source caller/clap inventory is separately recorded in
SOURCES.json; this report does not claim to have independently repeated every
one of those full-file reads. Applicable remaining checks: Python runner
regression, --locked library and feature-enabled
Cargo selection/tests, actual worker normal graph, canonical full and smoke gate.
No product code, test, script, build, Cargo or CI execution occurred.
