# Native read-cache controls at exact Core 1fc3ef2

Authored offline fixture against unchanged public Core APIs pinned to
`1fc3ef223d10322815dd9290a50d045bc95402bb`. Not a Core patch, upstream test suite,
security test or production journal operation. **At authoring: not yet built/run.**

`AgentAppServer::launch_resumed` is the native cache producer. It receives an
explicitly provider/module/plugin/command-free config. No model call, workflow,
turn or tool is invoked. Each child runs with fresh isolated HOME/XDG/TMP roots
and a small allowlisted environment; inherited credentials are not passed.
App-server shutdown is explicit. Config path is absent, so no profile watcher is
started. Native journal bytes must remain unchanged by cache creation/reopen.

## Authored cases

- New native cache, fresh-process `conversation_snapshot`, strict
  `load_projection`, `load_messages`, cold-store `usage_snapshot`, native app
  transcript; compare semantic history/revision and known empty usage data.
- Stale-revision rejection and late duplicate-message rejection leave canonical
  bytes and both cache files unchanged; a fresh process reads the same state.
- Successful append makes the view stale: `conversation_snapshot` must match
  strict updated history without rewriting the old view. Catalog may immediately
  return documented old display, then its bounded background refresh must expose
  new summary within the test deadline. Audit must return current canonical data.
- Separate native datasets for malformed cache, wrong checksum, cache schema
  mismatch and journal-schema mismatch in cache envelope. Only disposable cache
  bytes change; canonical journal hash must remain the original. Fresh snapshot
  falls back to exact canonical content.
- Separate native datasets for malformed canonical journal and wrong canonical
  record schema. Original files are retained. Strict projection, conversation,
  messages, cold usage and audit must reject. UI catalog intentionally may keep
  the old display. This distinction is not treated as a bug or execution authority.

All corruption is inside newly authored fixture data. The coordinator preserves
original native files and damaged bytes separately; no production data and no
attempt to forge a trusted cache or bypass identity/authority.

## Cache-hit evidence, separate from timing

Optional diagnostics run **only an owned child** under
`strace -f -qq -e trace=openat`; no read contents, unrelated process attachment or
permission workaround. Full child lifetime includes threads. A valid native
`snapshot` trace must open `.read-view.json` but not `journal.jsonl`. An explicit
strict projection positive control must open the journal. A schema-invalid cache
control must also open the journal. Tracer version/hash, argv, status and actual
paths are retained. If tracing is denied, do not retry via another tracer; mark
actual hit observation unavailable and retain source-derived labels.

Equivalent returned data alone is **not** proof of a cache hit.

## Measurements and limits

Untraced measurements use 64 and 256 one-part/256-byte messages, three fresh
process repetitions, three calls per API. Debug profile, shared host, warm-or-
unspecified page cache. Cumulative allocator-request bytes are not RSS; separate
relaxed counter loads are not one coherent atomic live-memory snapshot. Do not
infer precise alloc-minus-free values, p95, release latency, causal CPU savings
or production speedups. `usage_snapshot` on a directly opened cold SessionStore
is a different path from app-resume-populated metadata, and is named explicitly.

Each child: 120 s wall, 60 s CPU, 768 MiB address-space cap, 8 MiB per-file
limit (including trace logs). Disk reserve: 1 GiB.
Each output leaf must be new. Source, lock and binary hashes are captured before
and after the run and must match. No data cleanup is performed.

```sh
# Sole build owner; reuse existing exact-pin target and matching dependencies.
cargo fmt --manifest-path Cargo.toml --all --check
cargo build --offline --locked -j2 --manifest-path Cargo.toml
python3 run_cache_probe.py --binary "$CARGO_TARGET_DIR/debug/proteus-read-cache-probe" \
  --output ../results/current-cache-functional --stage functional --trace
python3 run_cache_probe.py --binary "$CARGO_TARGET_DIR/debug/proteus-read-cache-probe" \
  --output ../results/current-cache-measurements --stage measurements
```

Only run after the sole builder confirms available disk budget. A per-target
linker strip-debug option may be needed; record it explicitly if used and do not
compare timing to the older differently linked binary without qualification.
Execution-resume authority, nonempty model usage, concurrent writers, cache
capacity edges, cancellation and power-loss fault injection are not covered.
