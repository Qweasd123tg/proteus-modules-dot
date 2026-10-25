# Pinned MCP SDK boundary probes

A small **conformance probe**, not a Proteus module or MCP server product. It
separates raw JSON, the actual `rmcp = 3.3.0` typed boundary, and host-owned policy.
Consumers can reuse its authored fixtures as an SDK-upgrade gate before changing
Proteus lifecycle selection or metadata projection.

**Status:** 33 authored tests await execution. Lockfile generation and static
review are not runtime proof. See [VALIDATION.md](VALIDATION.md).

## What is exercised

| Suite | Cases | Boundary |
|---|---:|---|
| `typed_decode` | 12 | Actual SDK deserialize/serialize, not a handwritten DTO |
| `fixture_controls` | 2 | Authored responder rejects wrong phase/metadata/name/arguments and accepts valid controls |
| `lifecycle` | 19 | Actual SDK client against our child process over stdin/stdout |

The typed suite distinguishes supported fields (`outputSchema`, known
annotations, icons, title, `_meta`) from unknown top-level/annotation fields that
are dropped. It separates malformed **known** fields and duplicate known keys
from unknown-field tolerance. Preserving a JSON Schema object does not validate
that schema or validate call output against it.

The lifecycle suite covers Initialize, Discover, Auto, legacy-only/modern-only/
dual-era responders, exact request IDs and metadata, no common version, modern
capability/header rejection, wrong response shape, transport closure, failed
fallback, caller deadline, caller abort, unanswered discovery, a remote domain
error, and an MRTR intermediate response returned without hidden continuations.
Positive tool calls use the exact raw tool name and valid required arguments.
Tests assert observed child requests, not merely an `Err` or a wall-clock sleep.

### Two protocol eras, deliberately separate

- `execution.taskSupport` and top-level `tasks` capabilities in the legacy
  **2025-11-25 experimental tasks** shape are absent from these SDK DTOs. Their
  loss happens before a host can project a typed Tool. This does not allege that
  they are missing normative 2026 Tool fields.
- The modern **2026-07-28** shape uses explicit discovery, per-request context,
  `resultType`, MRTR, and a namespaced task extension. The probe distinguishes
  `complete` from `input_required`; it does not drive sampling, elicitation,
  task polling or follow-up tool calls.
- Knowing the string `2026-07-28` does not select Discover. The fixture checks the
  actual first wire method when default `.serve()` receives that date, matching
  Core's current API choice.

### Important fallback qualification

Pinned source classifies a non-modern JSON-RPC discovery rejection with either a
**matching ID or an omitted ID** as eligible for Auto fallback. A mismatched,
nonempty ID is a different error and must not fall back. Nearby SDK prose says
“correlated”; that shorthand misses the explicit omitted-ID branch. These are
separate fixtures. The fixture asserts the omitted-ID branch explicitly rather than relying on that shorthand.

The public SDK source fixes Auto's discovery budget at 10 seconds. One test uses
an outer 20-second budget and asserts unanswered discovery followed by legacy
initialization; it does **not** measure or prove the exact default duration. A
2-second caller deadline separately asserts that the child saw discovery but no
fallback initialization. These are semantic timeout checks, not benchmarks.

## Run in an approved build environment

```sh
bash ci/run.sh
```

Requires Rust 1.95.0 with rustfmt, Python 3.11+, Bash and GNU `timeout`. The gate
fetches only lockfile dependencies, then runs this package's authored tests
`--locked --offline`. Dependency acquisition may use the registry; test fixtures
have no network code. No upstream test suite, real MCP server, user hook or model
service is executed. The executable comes from Cargo's package-local binary path.

`ci-results/` must not already exist: each attempt gets a fresh evidence directory
(or choose a fresh `PROBE_RESULTS_DIR`). The gate verifies the reviewed source
hashes, runs eight authored Python verifier controls, and requires all 33 named
Rust cases plus exact suite totals with zero ignored/failed/filtered cases. It
compares source hashes before and after execution. Commands, exit codes, raw
stdout/stderr and compiler versions are retained, including failed runs. CI should upload this directory even
on failure. An enclosing job timeout is still required (suggested 10 minutes).
The package is standalone and has no Proteus source/path dependency.

## Scope limits

- This is **not actual Proteus Core integration**. It does not exercise Core's
  custom bounded transport, config decode, registry, alias projection, admission,
  process-generation invalidation, cancellation settlement, or provider output.
- The authored child allows 32 input frames, each at most 65,536 bytes including
  newline. Parent operation and cleanup waits are bounded. These fixture limits
  are not a claim about rmcp transport limits or hostile-server containment.
- Child kill/reap and SDK task joins are test cleanup, not proof that effects
  committed by a real tool were canceled. Caller future abortion is not a test of
  Core cancellation-token propagation.
- No reconnect/generation change, HTTP transport, pagination, task continuation,
  output-schema enforcement, or provider interoperability is claimed here.
- Remote annotations and metadata remain untrusted data, never approvals. The
  `example.invalid` icon URL and schema URI are retained strings, not fetched.

[HOST-SEAM.md](HOST-SEAM.md) describes the minimal proposed host-owned consumer
change and rejected module designs. [SOURCES.json](SOURCES.json) records exact
source paths, hashes, crate checksums and repository pins. No Core files changed.
