# Compact retained validation context — scoped correctness qualification

Status: **NOT_RUN for this package**. The source candidate has been independently reviewed;
a fresh exact-head hosted run and independent raw-artifact audit are still required.
This package is additive to personal-repository commit
`ad1f0a1c201b57602a6f572bc134061660e8ef31`; it does not modify that branch or main.

## Foundation and production delta

The exact current-graph foundation was qualified by
[run 40585800135, attempt 1](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40585800135)
on [PR 37](https://github.com/Qweasd123tg/proteus-modules-dot/pull/37).
Its shipping source tree is `9a122670d8e4360e4cdccc930569f141629baefc`.
That is historical evidence for the foundation, not a pass for the compact candidate.
All prior failed runs remain failures; this package never reclassifies them.

The new production patch changes three Rust files and canonical-turn-data documentation:
an additive contracts `ModelResponseValidationContext`, delegation from the existing public
validator without cloning tool specifications, and a compact per-request owned validation
snapshot in BoundModel/progress instead of retaining the entire request.
It retains final post-hook identity/tool validation, malformed terminal/failure handling,
accepted progress and the previously qualified empty-suffix shortcut.
No DTO, trait, wire protocol, public runtime profile, allocator or release build flags change.

The production tree is `8279b8f68ebb9d4076b5cb7c13c1ef75e3f5a02e`.
The two control trees are:
- baseline plus only its authored Core controls and cfg(test) allocator:
  `f9dabadd3dfbb1bc260f822aa9ad961257cb8670`;
- compact candidate plus the same Core controls/allocator and three contracts controls:
  `10dacc07a8242425c132f424aa264304321865be`.

All trees are reconstructed from pinned Core
`1f533a13f20a93bf164f7c8a169553b0b219bb51`, the complete qualified production recipe,
then the explicit compact patch recipe. Each full changed-blob map and complete tree
is verified before any source replacement. Existing executable modes are preserved.
The combined source author's test patch is an alternative to the two split test patches;
this package uses only the split versions and never applies both.

## Minimal fresh gate

Two source jobs run on standard `ubuntu-22.04` ephemeral runners, followed by a
receipt-only aggregate. Maximum source-job concurrency is two.

### Controls — no process fixture

1. Compile/list the exact default-feature Core library on the baseline tree:
   `cargo test --locked -p proteus-core --lib --no-run --message-format=json`.
2. Run five exact direct libtest cases, one at a time. Four must pass.
   `compact_stream_start_does_not_copy_historical_payload` must fail only at its
   source-bound historical-allocation assertion, with the expected positive
   small/large allocation diagnostics and large bytes exceeding small bytes plus 16 KiB.
   Compiler errors, timeouts, ignored/filtered tests, unrelated panics and startup failures
   are not intended reds.
3. Bind baseline source and executable postflight before changing the source tree.
4. Compile/list the candidate Core and contracts libraries with the same locked/default
   settings; run the same five Core cases plus the three candidate-only contracts cases.
   All eight must pass with exact names and no ignored substitute.

This is 13 executions of eight distinct authored test identities, not 13 distinct tests.
The counting allocator is cfg(test), thread-local and present only in these control arms.
These controls use local synthetic adapters/hooks and do not build or launch a module fixture.

### Pure candidate canonical full — once

The production arm has no authored compact test registration or counting allocator.
It retains already-reviewed cfg(test) support in the common foundation; this is not a claim
that the source contains no cfg(test) code.

Use the supported pinned runner once for compilation and once for execution:
```
python3 scripts/test.py full --no-run --message-format=json
python3 scripts/test.py full
```

The full run preserves the corrected 101 mandatory current-foundation identities and
adds all 49 existing compact-boundary cases observed in the qualified pure run:
26 BoundModel, 10 ModelService and 13 contracts canonical-response tests.
The union contains 150 mandatory names, with 80 bound to the Core library and 13
bound to the contracts library. Compiler artifact package/source/kind/default-feature
and executable pre/post hashes bind these to their actual Cargo target sections.
Protocol library/integration, all 16 module_swap cases, model_process and hook_runtime
also retain target-specific checks. The real follow-up ModelRequestRecorded witness,
lazy/display decode, settled unload/retained lease and live/next-request clear witnesses
remain mandatory. The focused-only empty-terminal-suffix envelope fixture is not falsely
required in this pure tree. Exact existing ignores remain explicit, never counted as passes.

No duplicate whole Core/protocol run, separate module_swap invocation, instrumented full
suite, old copy/cache/config negative matrix or stock Modules test rerun is added.

## Fixture provenance, not binary handoff

The pure full job freshly builds the reference fixture from stock Modules
`f5336923bcd01e581e64c4fbe84fa7f13388f5a5` through the supported
`PROTEUS_MODULES_SOURCE` override and `scripts/build_module.py`.
It verifies the exact Modules source tree, lock/manifests, all five locked Core SDK packages,
and metadata-derived stock Core `1f533a13` source. The stock SDK is not the patched host.
Core's default older `7fceaeb` fixture remains separately identified in the pinned
foundation manifest; no Cargo patch override or blind dependency-pin substitution occurs.

The freshly emitted reference binary is size/hash bound before and after canonical execution.
The unchanged DCP worker/module and four exact lock-declared tokenizer closure directories
are recorded pre/post solely as existing canonical regression dependencies. There is
no DCP feature work, optimization, advisory request, new npm test scope or dependency edit.
No cross-job binary handoff/cache optimization is mixed into this candidate.

## Controller and resource boundaries

The new wrapper hash-verifies and imports the qualified current-graph controller/manifest
from the immutable additive parent checkout, and the PR35 helper/recipe from immutable
public URLs. Imported top levels contain reviewed definitions/imports/constants and guarded
CLIs; the old orchestration is not invoked. It reuses exact patch application, source/tree
verification, bounded subprocess handling, compiler parsing, fixture provenance and canonical
parsers. The aggregate reparses current-run raw logs rather than trusting pass counts.

Source jobs: 150-minute job bound, 110-minute controller bound, two Cargo build jobs,
four inherited test threads; controls are direct single-test invocations.
Initial disk admission is 8 GiB; Runner stages sample a 2 GiB low-water floor.
Bounded raw output is at most 128 MiB per phase and each JSON result at most 4 MiB.
Setup/download/install stages have explicit step timeouts and bounded source downloads;
they are not represented as having the same Runner disk sampling.
No paid runner, secret inheritance, upstream writes, force push, cleanup or local build is used.
Official Rust 1.95.0, pinned official action revisions and the already-reviewed unprivileged
bubblewrap dependency are retained. Sandbox/Node setup is needed only in the canonical job.

Workflow push trigger is restricted to the separate compact branch and eight added files.
The older workflow's branch trigger is not activated. All current-run raw phase logs,
results and hosted controller self-test logs are retained even on failure.
Source/index, fixture/SDK and executable postflight are required; missing or foreign
head/run/attempt evidence cannot qualify. Exact infrastructure failures stay infrastructure
failures, not product results.

## What this does not establish

The intended red demonstrates allocation traffic caused by the old validation clone under
a controlled local test. It does **not** measure retained/live allocations, RSS, peak RAM,
startup latency or production throughput. There is no speedup percentage or unchanged-release
performance claim. Any later release speed/RAM experiment must compare the shipping trees
with the same unchanged release flags, features, allocator, model/module graph and workload,
without this counting allocator, and record separate runtime semantic and resource evidence.
