# Harness contract v1 — consistency gate, not a harness benchmark

This package contains an authored Python-standard-library validator, versioned
JSON manifest/result contracts, and in-memory positive/negative controls.
It contains no peer adapters and runs no Proteus, Codex, Pi or OpenCode runtime.
No comparative performance or real-model quality/cost result is supplied.

## What was executed

Only this package's authored pure-memory controls were executed with Python -B.
No upstream repository code, provider API, build, download, cache or filesystem write was
needed. The synthetic example is explicitly labeled synthetic-control and uses
example.invalid plus dummy hashes. It is not a runtime receipt.

## Commands

After separately reviewing and provisioning this source:

    python3 -B validator.py --self-test
    python3 -B validator.py --example
    python3 -B validator.py --expected-manifest-sha256 REVIEWED_SHA256 < input.json

The normal input has exactly two keys: manifest and result. --example prints
both complete versioned JSON objects. stdout is the result; no files are written.

The expected manifest digest is a caller-owned acceptance input, separate from
the producer's JSON. Review and freeze it before accepting results. Never derive
or refresh it automatically from the arriving result or manifest. A matching
digest establishes the caller-selected contract, not the caller's authority or
the truth of the recorded run.

Canonical hashes are SHA256 over UTF-8 JSON with sorted keys, compact separators,
ensure_ascii=False and allow_nan=False. These are not hashes of pretty-printed
JSON. Source-code hashes are hashes of the exact UTF-8 file bytes including its
final newline.

## Versioned JSON contracts

- proteus.harness.manifest/v1: scope, experiment/variant identity, exact input
  identities, parameters, report-only timing policy, and required named cases.
- proteus.harness.result/v1: manifest digest, identical input identities, declared
  evidence kind, and exactly one result for every manifest case.
- proteus.harness.validation/v1: consistency result, not runtime qualification.

The executable validator is the normative closed-field contract. Unknown fields,
unknown schema/status values, omitted/extra/duplicate cases, duplicate assertion
identities, and duplicate JSON keys are rejected. Every executed case includes
the six exact assertions: terminal, counts, effects, cancellation, egress,
settlement. PASS needs all six observed true, plus the validator's independent
cross-field checks; supplied assertion booleans alone cannot grant PASS.

Counters, resource observations and event ordinals are nonnegative signed-64-bit
integers, never booleans. Timing samples are finite nonnegative numbers. Input is
limited to 8 MiB. Deep/invalid JSON becomes INVALID, not a successful empty run.

## Identity definitions

source_repository/source_commit identify the primary source. They do not by
themselves describe a multi-repository assembly.

build_sha256 is the hash of the independently reviewable build inventory artifact,
covering every SUT binary/component and its flags; it must not silently cover only
the parent executable. lock_sha256 is the hash of the dependency-lock inventory,
covering all separate dependency graphs and exact dependency source pins.
toolchain and build_profile describe the selected build. adapter_sha256,
fixture_sha256, config_sha256, parameters_sha256 and environment_sha256 bind their
corresponding artifacts; route_id identifies the actual production entry route.

The caller must verify the inventories against the real assembly. The validator
checks syntax and equality of supplied hashes; it does not fetch artifacts,
authenticate hashes, prove inventory completeness or execute adapters.

## Observations and accounting

Model attempts have separate logical_id and attempt_id, outcome, start_seq and
terminal_seq. Multiple attempts for one logical request remain multiple attempts.
Tool calls have unique call_id, outcome and start/terminal sequence.
Outcomes are completed, failed, cancelled or inflight; only inflight has a null
terminal sequence. Counters are independently supplied and reconstructed from
these records; they must agree without dropping multiplicity.

Effect records retain operation identity, payload hash, committed/unknown outcome
and observation-only commit_seq. Unknown means unknown, never zero. PASS compares
the exact ordered semantic ledger with the manifest oracle, excluding commit_seq;
duplicate committed operations cannot disappear through set conversion.
The observed effect-ledger digest is recomputed. v1 supports ordered effect
oracles only: observed commit ordinals must increase in ledger order. An unordered
or intentionally order-insensitive parallel oracle must be predeclared unsupported
in v1. The validator never sorts actual effects into a passing semantic order.

All ordinals belong to one recorder's total order. Distinct represented events
have unique ordinals; each call's terminal follows its start. Effect commit and
tool terminal are represented as distinct events, even if wall-clock timestamps
coincide. Cancellation settlement aliases the one generic settled_seq; this is
the only intentional sequence alias.

Cancellation requested, acknowledged and settled are separate states. PASS after
cancellation requires actual settlement, not just an acknowledgment. Every
model/tool terminal and known effect commit precedes generic settlement.
A terminal cancellation cannot be followed by another model attempt. v1 does not
claim that every peer has the same no-dispatch barrier at cancellation-request or
acknowledgment time; exact expected attempt/tool counts still apply.

owned_processes_alive is measured after complete case teardown, not during an
ordinary warm turn. A case can time many warm turns before teardown. It accounts
for the declared SUT ownership set, including its workers/descendants; controller
and model-fixture processes are separate. PASS requires no owned processes or
inflight model/tool work left at that point. The process receipt must support the
ownership set and observation phase; a self-reported zero is not sufficient
external evidence.

Resource fields are nullable when unmeasured. cpu_ns covers the declared full SUT
ownership set; rss_peak_bytes is a synchronized aggregate sample peak, not the sum
of independent per-process high-water marks. pss_swappss_peak_bytes includes swap.
I/O and protocol bytes are separate observations. Missing observations stay null,
not zero. v1 validates their types, not their metrology or comparative performance.

## Evidence boundary and statuses

Trace, network, process and effect evidence references are mandatory for executed
observations. Only the supplied effect-ledger content is available for direct hash
recomputation. The other artifacts require independent inspection.

In particular, external_api_calls=0 is a recorder claim that must be backed by an
independently reviewed network receipt. A digest alone is not that review. This
validator does not establish the absence of network traffic.
R-scoped is a declared evidence category, not a promotion awarded by this program.
A pre-existing correctness receipt may be recorded only for its exact named scope;
missing required observations cannot be filled with invented zeros.

Validated reports explicitly say contract-consistency-only, evidence_authenticity
unverified, and qualification NOT_EVALUATED. Even a pinned PASS is not proof of
runtime execution, production compatibility, security, real provider billing,
speed improvement or harness ranking.

Exit codes:
- 0 PASS: every caller-pinned case has consistent passing evidence.
- 1 FAIL: at least one structurally valid failed case.
- 2 INVALID: malformed/inconsistent capture, missing caller pin, pin mismatch,
  or explicitly invalid result.
- 3 NOT_RUN: a required case was not executed.
- 4 UNSUPPORTED: unsupported case declared in the manifest before the run.

Aggregate precedence is INVALID > FAIL > NOT_RUN > UNSUPPORTED > PASS.

PASS/FAIL require executed=true. NOT_RUN/UNSUPPORTED require executed=false,
empty assertions, null observation and null timing. Non-PASS needs a reason.
UNSUPPORTED cannot be invented after a failure. FAIL records may truthfully retain
inflight/unknown/duplicated effects; the validator does not turn them into PASS or
erase them to satisfy the success oracle. Structurally inconsistent evidence is
INVALID rather than a usable runtime failure observation.

## Timing policy

v1 only accepts report-only timing. Samples may be null (unmeasured). It does not
accept precomputed quantiles, a calibrated=true assertion, performance budgets or
hard timing gates. A future calibrated-gating version needs reviewed A/A evidence,
matched route/build/config/environment, raw paired samples and order, sufficient
tail samples, and a predeclared noise/materiality rule. No such calibration or
cross-harness measurement is claimed here.
