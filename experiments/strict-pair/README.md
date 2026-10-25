# Strict JSON verification producer + Hermes-inspired gate

**Isolated paired feature; authored CI checks passed.** This workspace changes our
examples, not Proteus Core or any immutable upstream source snapshot. Earlier
v1 results are kept separately and are not evidence that this v2 code passed.

The producer verifies operator-configured JSON assertions using host-bound
`read_file`. The consumer now requires the **expected suite, exact config digest
and exact document/assertion coverage** before releasing its completion gate.
A different/easier suite, stale config, omitted check, duplicate or extra check
cannot satisfy strict policy merely by using the same configured tool name.

## Three small crates

* `json-contracts`: binary `proteus-example-json-contracts-strict`, export
  `verification.json_contracts`, tool/v6, existing host callback
  path. No direct file I/O, shell, network model, arbitrary tests or subprocesses.
* `hermes-verify-evidence`: binary `proteus-example-hermes-verify-evidence-strict`,
  our `hermes.verify_evidence` hook/v6 copy; existing
  canonical-history causality policy plus explicit receipt policy selection.
* `receipt-contract`: a shared **local example convention**, not a new SDK/Core
  capability. Typed v2 receipt, expected coverage and bounded validation.

## Explicit consumer policy — no downgrade

`receipt_policy` is mandatory:

```json
{
  "mode": "strict_json_contracts",
  "expected": {
    "expected_suite_id": "release-policy",
    "expected_config_sha256": "64 lower-case SHA256 hex digits from the helper",
    "documents": [{
      "document_id": "release",
      "path": "release.json",
      "assertions": [{"assertion_id":"no-publish","pointer":"/publish"}]
    }]
  }
}
```

The illustration's hash text is not valid configuration. Use the operator helper
below to generate real expectations from the actual producer configuration.
Strict mode requires `on_exhaustion = "error"`; it cannot silently release
unverified work after a nudge budget. The existing host continuation cap remains
independent and unchanged. An error is a workflow failure, not a new stop action.

`{"mode":"advisory_v1"}` explicitly selects the old unpinned v1 semantics. It
does **not** enforce suite/config/coverage and must not be used as the strict
manifest policy. It accepts only v1; strict mode accepts only v2. There is no
automatic schema detection, legacy fallback or default policy mode. The new
producer emits only v2. This explicit old mode is retained by owner request,
not offered as an equivalent reliability guarantee.

## Local v2 receipt

The authoritative object is only `metadata["proteus.example.verification"]`:

```text
schema_version = 2
status = "passed"
kind = "json_contracts"
cwd, verifier_call_id, suite_id, config_sha256
documents[]:
  document_id, configured_path, observed_path
  reader_call_id, content_sha256, bytes
  assertions_executed[]:
    assertion_id, pointer, check_id
```

Each `check_id` must exactly equal
`json:<suite>:<config_sha256>:<content_sha256>:<document_id>:<assertion_id>`.
The gate compares the receipt's verifier call ID with the current canonical
ToolResult ID, and cwd with the current host cwd. Document IDs/paths and assertion
IDs/pointers must match the configured **closed sets**: missing, duplicate or
unexpected members fail; permutation alone does not. Observed paths must match
`cwd.join(configured_path)`. Read-call IDs must be nonempty, bounded, unique, and
different from the outer verifier ID. Unknown receipt fields fail. Sibling audit
metadata cannot override a rejected receipt.

The config digest pins expected rule values, not just IDs. The generated expected
coverage additionally makes omission/duplication explicit; it is not inferred
from a producer's claimed count. The producer validates its emitted receipt
against the same shared contract before returning it.

## Operator workflow and runnable use case

Once compiled, from this workspace:

```sh
cargo test --workspace --locked --offline
cargo run -p proteus-example-json-contracts --locked --offline \
  --example strict_json_policy < json-contracts/fixtures/suite.json
cargo run -p proteus-example-json-contracts --locked --offline \
  --example strict_authored_fixture
cargo run -p proteus-example-json-contracts --locked --offline \
  --example strict_authored_fixture -- --fail
```

The stdin-only helper parses bounded JSON configuration and prints a complete
`receipt_policy` object derived from the producer's normalized typed config.
It does not install configuration, authorize tools or mutate host state. The
operator installs producer config and its matching expected policy together.
Changing rules, paths, IDs, suite, or config array order requires regenerating
the consumer expectation; stale expectations intentionally reject new receipts.

Executable and example target names are deliberately distinct from the frozen
v1 milestone, so a shared Cargo target does not overwrite its runnable artifacts.

The supplied release fixture checks version, draft channel, publishing disabled,
nonempty artifact list and an escaped-pointer string type. The negative example
changes the authored publish flag, produces a failed ToolResult and no receipt.
Examples use an explicitly synthetic host returning embedded authored bytes;
real assertions/hashes run, but no actual filesystem or Core run is implied.
Example process exit code is not verification evidence.

[profile.strict.fragment.toml](profile.strict.fragment.toml) and its
[expected-policy fixture](fixtures/expected-policy.json) are prepared with the
same five-check config. CI compared the compiled v2 Rust helper with both files
using type-aware JSON/TOML equality, and checked the positive receipt against
the authored bytes and all five assertion identities. This validates the supplied
configuration semantics, **not an actual Core host deployment**. The profile requires
the two binaries on PATH, a registered compatible read_file implementation and
the producer crate directory as cwd for the supplied fixture. Preserve the
existing registry, approval policy, hooks and permissions when merging it.

## What strict binding does not prove

* Trust remains in the selected producer, host canonical history, registered
  reader and output-transformation chain. Digests are **policy identity and
  observation correlation, not signatures or proof of honesty**. A consistent
  forged claim from a dishonest trusted producer remains undetectable.
* Only returned read bytes are checked. `AfterTool` may rewrite output while
  preserving metadata. Known partial/redacted/truncated forms fail, but hidden
  rewriting cannot be detected. No atomic multi-file snapshot, filesystem lock,
  current editor-state guarantee, or cryptographic read provenance is provided.
* The gate only covers configured mutators visible in retained canonical history.
  No visible mutation means policy not applicable, **not** all work verified.
  Compaction, omitted mutators, external concurrent writes and cross-turn retained
  evidence remain existing boundaries. Same-batch calls do not prove sequencing;
  a later failed verifier invalidates prior success. Pending/ambiguous calls fail
  to establish freshness. Call IDs are correlation, not anti-replay tokens.
* These are JSON assertions, **not arbitrary project tests or code correctness**.
  Operator-selected coverage can be weak. Strict policy enforces the configured
  choice; it cannot determine whether that choice is sufficient for a task.
* Core still owns permission admission, invocation identity/lineage, cancellation,
  journals, deadlines and settlement. No permission is granted by a receipt, hook
  continuation, config hash or `ReadOnly` label. No Core code is rewritten.

## Bounds and parsing

Producer limits remain: 16 documents, 128 total assertions, 64 KiB per observed
document, 256 KiB total, 64 KiB typed config, 512 KiB raw callback and 128 KiB
success result. IDs are 1–64 safe ASCII bytes; paths/pointers 512 bytes; cwd 4096
bytes; call IDs 256 bytes. JSON duplicate keys and depth above 32 edges fail.
`equals` excludes decimal/exponent/out-of-range numeric representations,
recursively, avoiding f64 rounding evidence; exact i64/u64 integers are supported.

Consumer preflight traverses an **already parsed borrowed Value** before cloning
or typed deserialization: bounded node/depth/collection/string/key counts and a
128 KiB serialized receipt counter. It does not bound allocations that already
occurred in SDK/host parsing. A configuration whose individually valid maxima
produce an oversized aggregate result is rejected, not truncated into success.
Strict consumer also rejects canceled/timed-out/truncated outer result flags.

## Validation status

Remote CI passed 81 workspace tests plus eight independent pairing tests, with
no failed or ignored tests, and the positive/negative/helper semantic controls.
No local v2 build or actual Core run is claimed. See [VALIDATION.md](VALIDATION.md)
for exact run evidence and limits, and [SOURCES.md](SOURCES.md) for pins.
