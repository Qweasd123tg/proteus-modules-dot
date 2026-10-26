# Reference tool catalog cache: isolated validation candidate

This additive bundle proposes one narrow reference-module optimization. It changes
no SDK trait, public wire DTO, slot, dependency pin, host authority check, or
runtime feature. It does not claim that arbitrary `ToolModule` implementations
have immutable getters.

## Exact graphs and provenance

- Bundle repository base: `Qweasd123tg/proteus-modules-dot@a0c1716756f8d5950dbf92638951f676bf8d2803`.
- Actual baseline: `Proteus-harness/Proteus-modules@0d9c5fd18f04e6e3a083351678065c5f72966792`.
- Both baseline and candidate keep its own Cargo.toml/Cargo.lock SDK graph:
  Core `f3d01053dff6113c31afbd885ef1ab1a8d931d53`.
- Separate interoperability scope uses host Core
  `63454d4e8b1e4e6b26d088fce2a17d46f30390ae`; its worker still uses the
  Modules-pinned `f3d0105` SDK. This is not a single unified current-Core graph.
- Preparation originally targeted Modules
  `f9fc92d37328b5dba51d270cc224ed0e6b95b43b` / Core
  `bee0e409e746e2df9db32748d4f8ea02201bd4af`.
  The unpublished, unexecuted 17,528-byte preparation patch had SHA-1
  `afa1d4bd85cec4e9874131729910bc3496c6a491`.
- The single shipped patch is 17,704 UTF-8 bytes, SHA-1
  `f06fd8942c338890e94d3d8b441a92d220c4da6a`, SHA-256
  `8ef892633cad6c1733257407ce0b2d6c52e982476386549977178f74b990c88f`.
  Only rustfmt layout changed since the independently reviewed preparation.
  It applies directly to the fresh baseline, without a second formatting layer.

The three modified upstream input blobs are identical at the old and fresh
Modules commits; the two new paths are absent at both. No registered tool,
context-provider, or policy source changed. Relevant tool/host/contract blobs
match across old, pinned-new, and current Core; the manifest records them.
The old dependency graph is provenance only, not a validation target.

## Behavior and tradeoff

Each loaded reference tool export snapshots its immutable registration-time
definitions. The catalog keeps original enumeration order and duplicate entries;
an index maps each exact public name to its first valid original implementation.
Duplicate rejection stays in the host. The first malformed definition still
fails listing with the original parse-error text; malformed definitions are not
dispatch candidates. Case and whitespace remain significant.

This removes repeated definition generation, JSON parsing, and linear name
search from invocation. Listing still clones/serializes definitions. It retains
parsed metadata, cached parse errors, and an index per loaded export, trading
resident memory for repeated work. There is no measured timing or RSS claim.
A new loaded export owns a new snapshot. Mutable/side-effectful generic getter
semantics are outside this reference-registry contract; do not generalize the
cache to arbitrary SDK plugins without a separate contract decision.

## Validation, not claimed results

At preparation time read-only source inspection, independent static review,
pure-stdin Rust 1.95 rustfmt, and Python/YAML syntax parsing were performed.
No build or product test ran on the low-disk preparation machine. CI must establish execution results for the
exact bundle commit; this document is not a passing CI report.

The isolated workflow uses two fresh Ubuntu jobs and official upstream runners:

1. `modules-pinned`: run unchanged-baseline real wire conformance, apply the
   candidate, run all seven catalog helper tests, then candidate real wire
   conformance. Every reference-package invocation of Modules
   `scripts/test.py` also prepares/runs the official Node hooks and DCP checks.
2. `current-host`: build the unchanged and patched workers separately in
   sequence through current Core `scripts/build_module.py`, then run current
   Core `scripts/test.py -p proteus-core --test module_swap` against each exact
   worker. DCP preparation resolves to the same checked-out Modules source.

Both scopes fetch immutable commits, check input/output Git blobs, preserve
Cargo.lock/manifests, use `--locked` through official runners, and verify that
the full pinned inventory and summary counts actually emitted successful
execution records (zero failed, ignored, or measured tests). A zero-test success
does not satisfy a gate. The fixture hash and source/index trees are recorded.
Separate target directories keep the host and worker graphs distinct.

Helper coverage includes ordered metadata and exact-name lookup, duplicate
first-match binding, malformed JSON and strict DTO errors, deferred host schema
validation, per-loaded-export ownership, repeated getter counts, and empty
catalogs. Existing real conformance is also extended to compare the tool list
before/after a real read_file invocation.

The helper work counter executes a **copied old lookup algorithm**, not an old
checkout. For its fixed 32-tool / 100 last-hit-and-miss-pair fixture it asserts
6,432 versus 32 spec getter calls (paired with parsing by the inspected paths).
That is deterministic source-path work accounting, not a latency benchmark or
evidence that the unchanged checkout ran the new helper tests. Actual baseline
behavior is covered independently by the existing official suites.

## Bounds and scope

- Read-only repository token; no upstream writes, merges, or releases.
- No reusable CI cache or shared target with other bundles; no local disk writes
  during preparation.
- Fresh runner roots only, no cleanup/deletion. Require 8 GiB initially and
  sample a 2 GiB free-space floor during commands; this is an abort guard, not
  a filesystem quota or a proof against allocations between samples.
- Two build jobs, four Rust test threads, 40-minute per-command and 120-minute
  per-job limits; attempted command cleanup adds at most 15 seconds and does not
  claim guaranteed process reclamation. Logs stream to Actions; result.json
  retains a 64 KiB tail per command and bounded test-name/summary evidence.
- Ubuntu's unprivileged-user-namespace setting is adjusted only in the ephemeral
  runner, following upstream's bubblewrap test prerequisites.
- No full-workspace, portable/Desktop, allocator, timing, or RSS validation is
  implied. This is a focused tool-catalog and process compatibility gate.

See `manifest.json` for all pinned identities and `validate.py` for exact
commands. A failed/missing baseline, missing named test, resource abort, changed
graph, or patch/hash mismatch fails the job instead of producing a PASS.
