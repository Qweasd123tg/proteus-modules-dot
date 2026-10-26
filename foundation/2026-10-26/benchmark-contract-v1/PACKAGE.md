# Packaging and reproduction

## Scope

This is a separate, additive research package for
`Qweasd123tg/proteus-modules-dot`. It does not modify any upstream Proteus
repository, module, existing workflow or performance patch.

The validator checks **contract consistency only**. Its successful structural
reports retain `evidence_authenticity=unverified` and
`qualification=NOT_EVALUATED`. The example and control results are synthetic;
they are not Proteus or peer executions, performance measurements, qualification
receipts or evidence of absent runtime egress.

## Exact reproduction

From this directory, using an independently reviewed copy of the package:

```sh
python3 -B reviewer_controls.py
python3 -B validator.py --self-test
python3 -B validator.py --expected-manifest-sha256 b9fe8d3c152aa3c04536f448449d90c0e7201e8b24e2d76a5dc7f2473328a510 < example.json
python3 -B validator.py --example
```

The reviewer command verifies the fixed validator source SHA-256 and byte length
before executing it; keep that check before direct validator invocations.

The literal digest above is frozen for this **synthetic example only**.
`example.json` contains both the versioned manifest and result;
`example.manifest.json` is the same manifest exposed separately for inspection.
A real run requires a separately reviewed, caller-owned manifest pin and actual
recorder receipts. Never copy this example's dummy identities into a real run,
auto-repin incoming results, or promote the synthetic controls to R-scoped.

`validator.py --self-test` runs 84 authored controls.
`reviewer_controls.py` checks the exact validator source digest, reruns those
84 controls, then runs 64 additional reviewer controls. The source code, not the
saved validation summaries, is the reproducible test.
`AUTHORED_VALIDATION.json` records the author's 84 controls and 16 CLI checks.
`REVIEWER_VALIDATION.json` records the independent review execution, not runtime
qualification. Some CLI cases overlap between author and reviewer suites;
their counts must not be added as unique coverage.

The consistency example exits 0; normal invalid, failed, not-run and unsupported
inputs exit 2, 1, 3 and 4 respectively. The control suites intentionally test these
nonzero result paths while succeeding only when expected behavior is observed.

## Isolated CI

`.github/workflows/benchmark-contract-v1.yml` is a new workflow. It triggers on
package/workflow changes pushed to `foundation/benchmark-contract-v1-20261026`.
Its job additionally checks that exact branch and repository, including manual
dispatch. It has no pull-request or main-branch trigger and changes no existing
workflow or upstream CI policy.

The job has read-only contents permission, a pinned checkout action with
persisted credentials disabled, a five-minute timeout, and Python stdlib checks.
It installs no package/compiler, uses no cache, invokes no external model/API,
and has no artifact-upload or write-permission step. GitHub provisioning and
checkout still require network; this is not a network-sandbox attestation.
The runner's Python version is printed, not claimed hermetically pinned.
The controls are correctness gates only; all harness timing remains report-only.

## Provenance and preservation

Preparation was memory-only: no local files, builds, clones, downloads or caches
were created. The authored source and control code alone were executed, with
Python bytecode writes disabled. Source documentation and repository metadata
were inspected through read-only connectors.

Base main was freshly read as
`a0c1716756f8d5950dbf92638951f676bf8d2803`, tree
`c43e62f41e4a2fa863c6ce0252752a625c0c4c9a`, on 2026-10-26.
The recursive tree response was complete, and none of this package's intended
paths or its workflow path existed at that base. Publication must recheck the
base and preserve the complete existing tree. This package author made no
external mutation and did not merge or change main.

`ARTIFACTS.json` lists exact SHA-256 hashes and UTF-8 byte lengths of every
included file except itself. These are transport/integrity checks, not proof of
trusted approval. The publication handoff separately pins the inventory bytes.
