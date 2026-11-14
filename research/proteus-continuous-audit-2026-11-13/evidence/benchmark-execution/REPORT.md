# Benchmark execution/provenance audit

Core inspected: `89997df995df7c39b713e16aba216ecb19c8f497`. GitHub main matched this SHA both before and after the pass. Audit checkout: `/workspace/shared/benchmark-execution-audit` (clean). Published result files were not changed. All new probes were offline with synthetic data; no model calls or real credentials.

## 1. `--binary` can hash one Proteus executable while running a different one

**Confirmed, P2.** `examples/performance/coding-harness/runner.py:202-204,234-235` resolves the supplied executable, validates it exists and records its SHA. However `adapters.py:82-83,144-145` mounts its parent directory and unconditionally returns `/runtime/bin/proteus`, ignoring the supplied basename.

Real execution reproduction, not just a mocked argv:
- Put two different owned dummy shell executables in one directory: `proteus-candidate` prints `candidate-selected`; `proteus` prints `sibling-executed`.
- Run the unchanged CLI with `--agent proteus --binary .../proteus-candidate --prepare-only`, a synthetic case and an empty synthetic auth JSON.
- `result.json` records `proteus-candidate` and its hash `7c84f5c13c128c79609965e8181f862f8ac79747a649583aae077eac57dc17fa`.
- Execute its prepared command through the real unchanged `runner.execute()` + bwrap: exit 0, stdout **`sibling-executed`**. Executed sibling hash is `cb21d8789ca4c7200a82bcf3855db5415ec1e1a587437e34401131a96c97a93e`.
- Direct control of the selected file prints `candidate-selected`.

Impact: a natural A/B test with renamed candidate binaries can benchmark the previous sibling while reporting the candidate hash. If no sibling `proteus` exists, it fails rather than running the validated executable. Ordinary default `bin/proteus` does not trigger this bug. This does **not** establish that historical published cells used a renamed binary.

Minimal fix direction: construct the inner executable from the resolved supplied basename, or mount the exact selected file at a controlled executable path. Regression must compare both marker outputs and provenance, not only prepared argv.

Stable source: https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/adapters.py#L82-L145

## 2. Runtime-unchanged proof misses changed executable dependency code

**Confirmed, P2.** `reconnect_runs.py:58-67` excludes all `node_modules` files except `package.json` in its outer condition, but its inner condition then excludes `package.json` too. Therefore installed JS code, package manifests and dependency links are absent from the snapshot. `cap_reruns.py:266,274-275` labels equality of these partial manifests `runtime-unchanged`.

Unchanged production helper reproduction:
- Construct a synthetic portable layout with an `.mjs` entry importing `node_modules/example-model/model-runtime.js`.
- Node prints `before`; capture `runtime_snapshot()`.
- Change only dependency JS bytes to print `after`; run Node again, then capture snapshot.
- Actual output changes **before → after**, implementation SHA changes, but snapshots are **exactly equal**.
- Positive control: change the top-level `.mjs` entry, and the same helper detects it.
- Snapshot keys contain only `bin/proteus` and the wrapper `.mjs`; even dependency `package.json` is omitted.

Tracked `examples/performance/results/reconnect-codex-cap-2026-11-12.json` currently contains `runtime.unchanged=true`, 60 selected hashes and zero `node_modules` paths. This is evidence of limited coverage, **not evidence that the historical installed runtime actually changed**. A lockfile hash alone does not verify the installed executable bytes.

Fix direction: either verify the installed execution/runtime content including dependencies and symlink targets, or rename/narrow the claim to exactly the selected manifest coverage. Add a behavior-changing dependency mutation negative control.

Stable source: https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/reconnect_runs.py#L58-L67
Consumer: https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/cap_reruns.py#L264-L275

## Evidence and controls

- `python3 /workspace/shared/benchmark-execution-evidence/repro.py`: pass; `result.json` includes both reproductions, SHA and marker controls. Python 3.12.14.
- Existing `runner_selfcheck.py`: **9/9 pass**, including real bwrap containment test.
- Existing `adapters_test.py`: **5/5 pass**.
- `git status --short`: empty.
- No compiler rebuild, provider benchmark or historical-data rewrite performed. No claim that these local defects invalidate old concrete benchmark totals.
