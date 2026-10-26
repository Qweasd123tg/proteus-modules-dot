# Fixed-history append groups at public Core 1fc3ef2

**Source-only: not yet built or executed against Core.** Twenty authored Python controller/semantic tests, sixteen synthetic artifact-gate
tests and four tiny owned-file archive controls have run locally. They are
not Core, tracing, process-termination or performance evidence.

This Rust fixture calls unchanged public `SessionStore::append_history` at exact
Core `1fc3ef223d10322815dd9290a50d045bc95402bb`. It compares legal API grouping, not a
Core patch or a newly discovered Core bug. Existing production callers already
batch: `runtime/history.rs:202` passes the complete new suffix;
`runtime/failed_history.rs:98` passes collected messages. In contrast,
`runtime/turn.rs:548` deliberately persists the current user message separately.
Nothing here recommends delaying that record, tool intent or effect barriers.

## Workload and controls

- One immutable 256-message corpus has fixed message/part UUIDs and exactly
  256 text bytes per message. Every child regenerates the expected DTO values and
  requires exact equality with the bounded input corpus. No hash-only acceptance
  of message/part identity. The full-run final-history serialized bytes must equal
  the corpus bytes; a fresh process reopens each committed session and checks exact
  history, per-record grouping, revision and sequence again.
- Pilot: 64 messages, groups of eight, then fresh reopen.
- Separate validation controls: after a seed message, two new messages followed
  by a duplicate of the active seed; and two new messages followed by a duplicate
  of the first incoming message. Both require the specific duplicate-message
  terminal error leaf naming the exact expected duplicate UUID, byte-identical
  journal and unchanged projection. Before/after-rejection bytes are separately
  retained for independent artifact comparison. Reusing the exact
  valid prefix afterward must succeed with sequence/revision two, proving no
  consumed sequence or candidate-ID poisoning at these public boundaries.
- Matrix: 256 messages, group sizes 1/8/64/256, three fresh process/session runs
  per size, each followed by a separate fresh-process reopen. 256/32/4/1 records
  are expected, intentionally **not the same transaction history**.
- Every stored payload must remain inline and below the pinned 256-KiB threshold.
  A blob-storage crossover aborts the row instead of confounding the comparison.
- Exactly 29 authored child invocations: corpus generator, pilot + reopen, two
  rollback controls, twelve workloads + twelve fresh reopens. No external process
  hooks, model/provider/tool calls, production data or upstream suite.

## Measurements and what they cannot establish

Each append's process-wide allocator-request counters and elapsed nanoseconds are
recorded separately. Corpus loading/construction and all validation/file evidence
are outside those intervals. Core's own slice clone, validation, record encoding,
write/flush/sync remain inside. First append includes cold writer initialization;
group256 has only that one call, so no pretend steady-state sample is reported.
Separate relaxed counters are not a coherent live-memory snapshot. Requested bytes
are not RSS, actual copied bytes or exact alloc-minus-free values.

The matrix has identical final history but different intermediate revisions,
atomic group sizes, failure exposure and durable/crash visibility boundaries.
A lower requested-byte total would be API cost/consumer-design evidence only for
consumers already holding genuinely atomic groups. It is not a general Core
speedup, same-semantics drop-in optimization, per-token result, isolated fsync time,
release latency, p95 or production SLA. No effect/authority/admission/cancellation
or power-loss behavior is tested or weakened. Never batch across such barriers.

## Limits and execution

Fresh output leaf only; no evidence cleanup. Each child uses isolated HOME/XDG/TMP
and an allowlisted environment, a fresh process group, 60-second wall cap,
30-second CPU cap, 512-MiB address-space cap and 8-MiB per-file cap. Timeout kills
only the owned process group and uses bounded output drain; no arbitrary spawned
modules/process trees exist in this config. The 8-MiB retained stdout/stderr cap
is checked after communicate(): it is **not** a hard pipe-capture memory bound.
This fixed authored probe emits at most256 small samples and no corpus bodies.
Child RLIMIT_FSIZE bounds regular file writes, not pipe buffers. Corpus cap 2 MiB. Preserve at least
1 GiB free disk. All source, lock, binary and corpus hashes are retained/rechecked.

Only the sole builder/authorized CI queue may run Cargo. The lock was seeded from
the accepted exact-pin read-cache package with only our root package renamed;
actual locked resolution/build is still pending. Same dependency set/profile.

```sh
python3 -B -I test_group_controls.py -v   # mocks/synthetic only
cargo +1.95.0 fmt --check --manifest-path Cargo.toml
cargo +1.95.0 build --locked -j2 --manifest-path Cargo.toml
python3 -B -I run_group_probe.py \
  --binary "$CARGO_TARGET_DIR/debug/proteus-append-group-probe" \
  --output /fresh/owned/validation/append-groups
```

Keep failed raw outputs and exact build head/commands. A successful fixture is not
independent reviewer acceptance. Reconcile measured claims only after execution.

## CI-only handoff and independent artifact checks

No remote write is authorized by this README. The coordinator currently holds new
unrun-package publication pending explicit experimental-CI permission. Source
review and local pure controls can proceed; Cargo/Core execution remains NOT RUN.

`ci/verify_group_artifacts.py` checks all29 exact child names/argv/exits, source and
binary identities, typed JSON equality and every aggregate. Its separate literal
DTO construction validates the exact fixed corpus. It inspects each generated
inline journal's groups, revisions/sequences and exact message/part values, and
compares retained rejection bytes. This is a fixed-fixture receipt inspector, not
a replacement Core validator or independent re-execution of Core.

`ci/archive_evidence.py` is the reviewed native-cache packager with only its
archive root label changed to `append-groups`; it rejects links/nonregular files,
bounds files to8MiB/aggregate256MiB, preserves pipe-containing Core paths, hashes
and rereads every payload, and never deletes source evidence. The copied sole-
builder `ci/guarded_build.py` is byte-identical to the shared approved build owner
helper; offline locked build stops at its sampled1GiB+128MiB free-space threshold.
The proposed workflow first requires8GiB free and performs an explicit locked
dependency fetch. Actual CI execution, including any compiler/runtime failure,
must be retained before any result is described as measured.
