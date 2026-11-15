> Package mapping: reviewed `01-binding-owned-call.patch` is published byte-identically as `patches/core-binding-owned-call.patch`. Reviewed `02-insertion-driven-revision-HOLD.patch` is published under `hold/`, outside the recommended composition.

# Independent exact-source review of the split

Base: Core `a3b82a676aa66a7a6b392dc45a29560590fd9b61`. Both target files were independently fetched at this exact commit and match the previous reviewed preimages: `history_capture.rs` Git blob `dbd8801b74d61be313ad1bf1e86146eb25cc4a2c`; `checkpoint.rs` Git blob `5aa717381e5e51de30a4f281a888ada7220b790c`.

This review covers the exact two patches below. It is not compilation, test execution, a benchmark or production integration approval.

## 01-binding-owned-call.patch

SHA-256: `ecc1160a3288aa7e7e7935a8843ec4677eb3e0dea3a8cd5e7f00c16a39d18cc5`.

No source blocker found in the inspected change. The removed ToolCall is constructed only by cloning `binding.execution_call`, and it is not independently mutated. All subsequent lookup/comparison operations address the same call through the retained binding. Complete execution identity, raw arguments, ordering, partial acknowledgments, reserved message/part identities, and error precedence remain intact. The model call is not substituted for the execution call.

Private derived Debug tuple formatting changes, as must be disclosed. Public DTO/wire shapes are untouched. This patch does not change checkpoint revision detection and does not include patch 02 by implication. Existing tests remain present and do not access the removed tuple layout; they have not been run.

## 02-insertion-driven-revision-HOLD.patch

SHA-256: `6265beec1edda9e23f0fa8adbafb0ed4c5bbb2dc5cea4c95f5817f83fd86e311`.

Keep this separate and on HOLD as a behavior-change proposal, not a completely behavior-preserving cleanup. Canonical history uses derived PartialEq, while ContextChunk and hosted file-search result scores expose floating-point values. A native value containing NaN is not equal to its clone. Thus clone/equality can spuriously advance revision on an unbound no-op result, while the new insertion boolean does not. This is a source-level native-type counterexample to an unconditional equivalence claim, not a demonstrated reachable stock-provider/JSON incident.

The bool implementation appears preferable to reproducing a spurious revision increment, but requires an explicit scope/policy statement and a native in-memory boundary check. A JSON-only process fixture does not exercise NaN faithfully. Reuse/extend an appropriate existing native boundary test rather than introducing a parallel synthetic framework. Do not reinstate full-history cloning solely to emulate this accidental case.

For reflexive histories, inspected revision behavior is preserved: false means no binding/no insertion; true means exactly one insertion; `|=` does not short-circuit batch processing. A changed successful batch still increments once. A late error still exits before revision increment after earlier insertions and still drops the rest of the drained effects. This existing partial-mutation/error behavior is not repaired. Attribution, external recorder ordering, durable-store ownership, lock ordering and await/cancellation boundaries are unchanged.

## Independent verification and limits

Rehashed both split patches. Applied each in a separate review copy with strict `git apply --check --whitespace=error-all` and GNU patch `--fuzz=0`; no offsets occurred. Each target exactly matches its portion of the previously reviewed combined candidate. Reverse application restored exact base bytes. The split introduces no new source edits.

Rust, Cargo, rustfmt, native/provider/runtime tests and benchmarks were NOT RUN. Upstream was not changed. The patches and source identities, not surrounding in-progress documentation, were the subject of this exact review.
