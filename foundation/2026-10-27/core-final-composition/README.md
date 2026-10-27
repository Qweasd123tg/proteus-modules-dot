# Final pure foundation composition

This lane runs **one canonical full gate** on exact Core source tree
`44021ca3f2cdf91046345460709a254f04299e52`. It is a correctness gate, not a performance benchmark.

## Exact source

The pinned upstream is Core `1f533a13f20a93bf164f7c8a169553b0b219bb51`.
The already-qualified current-graph foundation is `9a122670d8e4360e4cdccc930569f141629baefc`
(PR37, run 40585800135 attempt 1). This composition adds only:

1. The reviewed compact model-response validation context (pure compact tree
   `8279b8f68ebb9d4076b5cb7c13c1ef75e3f5a02e`).
2. The existing `broker_v3` test's pending-callback precondition and operation/actual-terminal
   diagnostics. Strict Protocol, generation increment, and zero-pending-state assertions remain.
3. The five-line removal of the duplicate raw-argument JSON parse in `bound_tools.rs`.
   The reviewed validation and execution boundaries remain in place.

There are six changed paths relative to the qualified foundation, 42 relative to pinned upstream.
The final tree contains no new compact/raw mechanism-test files or counting allocator.
The user's lazy display/resume, settled-history unloading, hibernation and retained ownership
behavior are preserved. Earlier disclosed config and model-process fixture amendments remain.

## One bounded current-tree gate

- Standard `ubuntu-22.04`, exact Rust 1.95.0, build jobs 2 and test threads 4.
- Reconstruct/hash the complete source tree before materialization; check formatting.
- Build fresh reference fixtures from the explicit supported Modules
  `f5336923bcd01e581e64c4fbe84fa7f13388f5a5` source override, with locked stock Core SDK
  `1f533a13` provenance. This is not a claim that stock Modules tests exercise the patched host.
- Prepare unchanged DCP only as the canonical runner's regression dependency. No DCP
  development, npm advisory call, standalone npm suite, or dependency update is included.
- Use the pinned runner's `scripts/test.py full --no-run --message-format=json`, then exactly
  one `scripts/test.py full`.
- Require 177 existing named witnesses, including 92 Core and 15 contracts requirements,
  all 21 broker cases and all 13 execution-boundary cases in their actual compiler-bound
  target sections. Preserve hook next-model, model-process, module-swap, lazy/history,
  ownership, recovery and sandbox witnesses and the exact inherited ignore set.
- Recheck source/tree, fixture source/locks/binaries/installed closure, and every selected
  canonical executable after execution. A separate same-job step reparses bounded raw
  evidence and binds repository, workflow, head, run, attempt and publication tree.

The immutable compact/current-graph controllers are imported only as hash-verified helpers;
their former source-phase orchestration is not invoked. In-memory source-plan reconstruction
may check old recipe data, but only the final pure arm is materialized, compiled and run.

No old baseline matrix, instrumented full library suite, separate broker/protocol/module-swap
rerun, or stock Modules `codex_compaction`/`codex_model_resume` suite is repeated.
No binary-handoff/build optimization is mixed into this gate. Shipping release flags are unchanged.

## Evidence boundaries

PR39 run 40591725260 remains **failed**: compact baseline had four green cases and one genuine
expected allocation-assertion red; candidate had eight green cases, but canonical `broker_v3`
failed and final postflights were not reached. That failure's actual operation/terminal was not logged.
The source-backed pending-callback test repair does not prove retrospective causation.

PR40 run 40594880289 separately passed all 21 broker cases with source/binary postflights.
PR42 run 40597152517 attempt 1 separately passed the raw-parse target gate: 41 green
executions covering 34 distinct cases, with exact source/fixture/executable postflights.
Its pure, baseline-semantic and candidate-semantic arms are historical scoped prerequisites,
not fresh executions on this final composed tree.
Historical targeted passes do not substitute for the fresh full-tree result here.

The final disposition starts **NOT_RUN**. Only successful exact-head source and raw-audit steps,
a successful hosted job, and independent raw-artifact review can establish full qualification.
All earlier failed runs remain failures. Allocation traffic controls are not retained/live/RSS
measurements; this lane makes no release speed, RAM, throughput or latency claim.

## Bounds and publication

One ephemeral source job, 150-minute job limit, 6600-second controller budget, 1800 seconds each
for canonical compile and full run, 8 GiB initial and 2 GiB low-water disk limits, 128 MiB total
controller output and 4 MiB receipt cap. Setup/download steps have their own time/size bounds;
they are not represented as having the Runner's per-process disk sampling.
No cleanup, paid runner, secrets, upstream write, merge or deployment is performed.
Bounded setup/self-control/source/audit evidence is retained even on failure.

Publication is additive on a separately guarded personal-repository draft branch.
All inherited files remain unchanged; parent PRs and main are not mutated.
