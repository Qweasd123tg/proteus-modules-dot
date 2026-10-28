# Isolated plan component — source-bound candidate

This is a **draft qualification lane**, not an already verified release or a measured speedup.
The existing aggregate reference executable remains the default. This patch extracts the shared
Tool adapter and adds an opt-in `proteus-plan-module`, retaining the same `plan_tool` module ID,
contract authority, config, SDK pin and implementation. The upstream documentation patch shows
the explicit component-command replacement; it does not silently change existing profiles.

## Immutable source

- Modules: `56571639c804443dbca58e054fff8631ecb8b312`, tree `93d0c3eb6fbd6a94c03d2abb88a6bd37e7eb287a`.
- SDK/Core dependency: `1f533a13f20a93bf164f7c8a169553b0b219bb51` (unchanged).
- Patch SHA-256: `f41c36ff8105d2b69126edeccd5a969a4c8eadadd12219bf5e4c268392563aaa`.
- Expected full post-apply tree: `c9cd2dba678bdda0c405ec2a04a7f26483de3e71`.

The full candidate tree was computed from the exact untruncated upstream tree and the frozen
16-path source delta; recomputing the baseline yielded the pinned upstream tree. CI must verify
this expected identity by `git write-tree` after exact shallow fetch, checkout and `git apply --index`.
The JSON source manifest records pre/post SHA-256 for every changed path. The payload manifest
binds the patch, controller, tests, graph evidence and wire probe. The Actions checkout commit/tree
and exact compiler version, commands, logs, status and duration are recorded in `result.json`.

## Bounded selected validation

One dedicated branch push starts one job. No `pull_request` or manual trigger is installed.
The branch is `ci/component-split-20261028`; paths are confined to this directory and its workflow.
The 41 inherited workflows at delivery base `03d0d69780f848f564198ad82cdec4f2ff45bd81`
were read and Git-blob verified: none matches this branch/path combination, the draft PR changes,
or the same paths on a merge push to main. The delivery workflow does not run on main.

Limits: Ubuntu 24.04; Rust **1.95.0**; two Cargo jobs and two test threads; one fresh source and target;
25-minute job, 20-minute controller, finite per-command deadlines/output bounds; no automatic retry,
Cargo network retry, dependency/target cache, Cargo profile changes or native dependency installation.
An exhausted budget is failure, not an invitation to restart or silently omit checks.

Required stages:

1. Verify exact delivery payload; fetch the exact Modules commit/tree; verify source preimages,
   apply the exact patch, verify changed paths, whitespace, postimages and complete candidate tree.
2. Run the source-bound declared normal/build dependency graph + lockfile delta checker,
   controller synthetic tests and wire-controller synthetic/fake-child tests.
3. `cargo +1.95.0 fmt --check -p proteus-tool-adapter -p proteus-plan-module -p proteus-reference-module`.
   Formatting failure is required failure **but does not suppress independent compile diagnostics**.
4. Separate `cargo tree --locked --edges normal,build` calls for the standalone and reference packages,
   retaining raw trees/features and parsed package sets. The standalone rejects an aggregate, Core
   runtime, Desktop or unrelated tool dependency. These are selected dependency graphs, **not exact
   compiled-unit proof** ([Cargo documentation](https://doc.rust-lang.org/cargo/commands/cargo-tree.html)).
5. `cargo test --locked -p proteus-tool-adapter --lib` and
   `cargo test --locked -p proteus-plan-module --bin proteus-plan-module` (14 source unit tests planned).
6. Separate default-release `cargo build --locked --release -p PACKAGE --bin PACKAGE` for
   `proteus-plan-module` and `proteus-reference-module`; no full-workspace or aggregate test run.
   Cargo JSON `compiler-artifact` is matched to the exact `cargo pkgid`, executable target,
   source path, non-test profile and fresh selected target directory. Artifact SHA-256 and sizes
   are recorded before and after the wire run.
7. The selected two binaries undergo the bounded differential wire probe: positive default/config
   cases and fresh-process rejection cases; repeated/malformed/unknown calls; exact manifest,
   identity/schema/features and reply comparison; no serviced callbacks, models or network services.
   The probe caps its suite at 120 seconds (+ bounded cleanup), each request at 5 seconds,
   stdout at 4 MiB/process, stderr at 128 KiB/process, frames at 1 MiB/64 per process.
8. Require unchanged artifact identities, Cargo.lock/postimages and full source tree afterwards.

Every required failed, timed-out or never-run stage keeps the final result **failed**. The artifact
upload runs even after failure and contains only bounded evidence, not source checkouts/binaries/caches.
No Core/Desktop executable, upstream full runner, portable packaging, DCP preparation, model run,
benchmark, deployment, upstream repository edit or merge is performed by this lane.

## Verification status before hosted CI

Local work was source-only: no Cargo/rustfmt available and no local builds/clones performed.
The candidate patch, manifests, lock delta, copied catalog/test identities and graph were reviewed.
Controller tests are synthetic; the wire-controller tests use self-authored fake children only.
Neither is a claim that real Rust binaries compile or pass. Hosted results for the exact published
commit must be read before qualification or any separately authorized merge. The source instructions'
full/portable runners are deliberately **not** run under this narrower authorized resource scope.
