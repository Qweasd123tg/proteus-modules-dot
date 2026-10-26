# Validation — source-only, no YAML runtime results

As of 2026-10-26:

| Stage | Observed status |
|---|---|
| Cargo.lock resolution | Passed, 55 registry packages |
| Locked source fetch | Passed through the coordinated build queue; no source execution |
| Parser archive checksums | All three independently matched to lock |
| Exact candidate API inspection | Completed read-only; hashes in SOURCE_PINS.json |
| Final Rust fmt/check | Passed; frozen baseline copies unchanged |
| Locked offline full metadata + feature/checksum verifier | Passed; exactly saphyr comments+deserialize |
| Synthetic verifier controls | 20 passed |
| Authored Python child capture controls | 4 passed |
| Mocked Cargo disk/deadline guard controls | 7 passed; no Cargo invocation |
| Synthetic exact-helper-log controls | 4 passed |
| Rust compilation | **Not run** |
| 159 semantic/envelope child invocations | **Not run** |
| 15 budget child invocations | **Not run** |
| Complete native/runtime CI gate | **Not run** |
| Parser migration / module change | **Not performed or accepted** |

The synthetic controls construct verifier inputs directly; they do not parse YAML
or establish expected language semantics for ambiguous cases. Capture controls run
only four tiny authored Python strings. These thirty-five helper controls must never be
reported as Rust parser tests.

Local native compilation remains blocked by the shared disk reserve. New
experimental CI publication is held pending user authorization clarification;
there is no parser branch or CI run to cite. No alternate publication route or
resource-guard bypass was attempted.

Before a runtime result can be accepted: freeze/review the exact controller and
source inputs, execute the full locked gate, preserve failures, reconcile all
174 child receipts with source/binary identities, and review differences rather
than treating observation-integrity success as migration approval.
