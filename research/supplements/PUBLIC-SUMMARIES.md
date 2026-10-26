# Supplemental validation: delivery index

This is a **documentation candidate**, not a new test run or a published test
package. The source links below identify already published immutable baselines.
The supplemental harnesses and historical evidence are retained separately;
`PUBLIC-INDEX.json` identifies their exact hashes, **not public download links**.
Proposed target paths in that index do not yet exist in the published baseline.

## What the additional evidence establishes

| Subject | Historical accepted execution or review | Deliberate boundary |
|---|---|---|
| [Pi ready steps](https://github.com/Qweasd123tg/proteus-modules-dot/tree/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/pi-ready-steps) | 4,086 tool cases + 2 setup RPC; 4,013 successful advisory results, 53 typed plan errors and 20 SDK errors. Independent small-DAG oracle and targeted invalid-input controls. | At most four nodes; not exhaustive over all four-node graph/status combinations. Immediate dependency states are caller-supplied, not verified history. No execution or authority grant. |
| [Letta evidence blocks](https://github.com/Qweasd123tg/proteus-modules-dot/tree/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks) | 398 requests across 98 direct workers; 295 complete projections, four exact request errors, one null catalog result, 92 successful initializations and six diagnosed factory failures. | Supplied-block projection, not upstream Letta, persistent memory or source authenticity. Revision/scope/tombstone selection and UTF-8 budgets are finite fixture coverage. |
| [Original Hermes v1](https://github.com/Qweasd123tg/proteus-modules-dot/tree/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/hermes-verify-evidence) | 909 hook cases + 5 initialization RPC; 101 Continue, 793 nudges, 15 intended errors. Includes 810 ordering cases and 99 targeted controls. | Authored history/receipts, not actual Core or verifier execution. Continue is not necessarily a verification verdict. **No v2 expected-suite/config/coverage guarantee.** |
| [Claude command-hooks adapter](https://github.com/Qweasd123tg/proteus-modules-dot/tree/fdcd5687a5a510732396d1c0bc0b9a0cc61d821a/hook/claude-command-hooks) | 51 cases / 48 hook invocations through the pinned adapter and JS SDK; 52 controller frames, 41 fixture-ready identities, 37 completed-write records and 18 targeted errors. | Only a fixed harmless authored exec-form fixture. Not real user hooks, full Claude plugin parity, Core policy/approval or an OS process-tree audit. |
| [Original 90-finding catalog](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/research/catalog.json) | Targeted status reconciliation: 28 selected rows (3 still supported, 18 refined, 7 with runtime-scoped evidence added); 62 explicitly not rechecked. | No fresh 90-item audit or new product execution. Original wording, 44 rejected hypotheses and six rejected shortcuts stay historical; no rejected hypothesis is revived. |

The probe-control suites are separate from module calls: Pi 27, Letta 26 pure +
8 transport mocks (plus a reviewer's boundary control), Hermes 39, Claude 25 Node
+ 13 Python pure/mocked controls. These are not additional product scenarios.
Original baseline tests are not added again to the supplemental counts.

No original module defect was reproduced by these four bounded supplemental
probe corpora. Harness corrections were reviewed before the corresponding run;
this is not an arbitrary-input correctness or security guarantee. Runtime results
were independently checked from retained owner artifacts, not independently
rerun by the reviewer. No cross-module end-to-end result is inferred.

## Read the evidence at its actual layer

- Pi and Letta retain decoded outer frames, not byte-for-byte raw stdout. Pi also
  preserves the original inner output strings. Hermes retains raw outer stdout
  with worker/frame offsets. Claude retains raw controller frames and small
  fixture completion records, **not copies of large fixture output streams**.
- The Rust probes used captured direct `Popen` children and no serviced host
  callbacks. Their empty owned directories and reaped children are not an OS
  sandbox or general descendant-cleanup proof.
- Claude's SDK owned its fixture child/process-group signaling. Ready records
  are not a syscall spawn census. Post-settlement PID probes did not signal PIDs;
  they do not establish PID-lease-safe SDK signaling, all-descendant cleanup or
  hard blocked-I/O bounds. Timeout/cancel negatives required a ready record,
  the exact diagnostic and paired uncanceled completion controls.
- Hermes v1 accepts a nonempty bounded check list from its configured verifier,
  not an expected suite. Duplicate names and unrelated top-level markers have
  the published v1 semantics; this supplement must not inherit strict-v2 claims.
- The catalog delta separates source persistence, runtime evidence and remedy
  adoption. A native Core observation, SDK fixture, authored alternative and
  source-only proposal are not interchangeable. Selected pin comparisons are
  not whole-tree or latest-upstream claims.

## Historical identity is not portable execution authority

The executable SHA256 values identify the **historically observed local bytes**.
They neither authenticate a new executable nor prove that any particular build
will reproduce those bytes. A source commit/hash and an executable hash alone
are not a reproducible-build attestation. The Node executable hash has the same
historical limitation.

A future portable harness needs a separately trusted, explicitly reviewed
source/lock/toolchain/build record and a new execution receipt. It must never
learn a binary hash from whatever path was supplied and call that validation.
Keep the old run and the new run distinct even when all functional results match.
See [RETEST-OBLIGATIONS.md](RETEST-OBLIGATIONS.md) before adapting paths, imports,
pins, fixtures, validators, deadlines or artifact schemas.

The retained pre-execution snapshots intentionally still say “unrun.” Their
later runtime review identifies the executed bytes; history was not rewritten.
This candidate introduces no new build, module invocation, remote check or
publication. Immutable URLs are derived from retained accepted commit mappings,
not a fresh reachability check of those links.
