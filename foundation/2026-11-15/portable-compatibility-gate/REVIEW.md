# Independent source and execution-evidence review

Verdict: no blocking issue found in this bounded remediation of the already
known joint Desktop/Extensions packaging compatibility gap. This is not a new
finding, upstream integration, native runtime validation or release approval.

## Source review

Reviewed both changed production files, the complete 259-line regression
module and the BUILDING documentation. The final gate reads the completed
stage record, checks shipped extension protocol and required features against
that stage's Desktop metadata, and runs before publication. The original
structural base check remains unchanged, so jointly updating Desktop and
extensions can repair an incompatible input base. Rebuilding Desktop can
restore missing provenance. Unrepaired missing metadata now rejects core-only
updates and reuse; this deliberate tightening is described in the documentation.

The separate helper import does not change behavior and avoids modifying the
long original import context used by the serialization proposal. Documentation
was subsequently moved below the existing build-failure paragraph; the reviewed
production and regression bytes did not change. The alternative after #142
adapts only its synthetic serialization fixture: it stubs the new gate alongside
the already stubbed completeness checks, then checks gate call order and lock
coverage. This does not bypass production validation; the new compatibility
suite uses the real gate on the combined tree.

The test loader scopes replacement modules to import/call boundaries. The full
assembly branch's delayed NOTICE_README import is covered. Unexpected subprocess
calls fail explicitly. The tested main, assembly orchestration, stage validation,
hash collection and publication functions are real project functions, operating
on owned inert fixture files. Builders, source resolution, notice installation,
source identity and full manifest production are synthetic replacements.

## Actual evidence inspected

- Candidate log: 12 test methods pass, with no failures, errors or skips; exit 0.
- Pristine baseline with the same regression file: four explicitly selected
  methods fail with AssertionError: SystemExit not raised; exit 1. These are
  expected regression failures, not loader errors or passing tests.
- Therefore there are 12 distinct candidate methods and four repeated baseline
  executions, not 16 passing or 16 distinct tests. Subtests are not extra methods.
- Combined-tree logs: the same 12 compatibility methods and six adapted
  serialization methods pass, with exit 0 for both suites. This gives 18 methods
  in that tree, not 30 unique methods or 30 new regressions across both trees.
- Independently recomputed the five baseline Git blob identities and SHA-256
  values against SOURCES.json; all match.
- Independently recomputed final production/regression hashes against saved
  execution-input records; all match. BUILDING is the sole differing candidate
  input, reflecting the reviewed documentation relocation after execution.
- Independently matched both final patch digests and the combined-tree source
  hashes to VERIFICATION.json. Read the recorded strict whitespace apply checks,
  zero-fuzz application/reversal and five-target composition comparison.
  The two standalone patch orders use line offsets in places, not fuzz; this is
  target-file identity, not a whole-checkout or runtime equivalence claim.
- Read the recorded #161 manifest-pair check: protocol remains 4, old Desktop
  metadata rejects the required active-pane feature and coordinated metadata
  accepts it. These are two helper outcomes, not Rust tests or handshakes.

The reviewer read the actual logs and checked bytes but did not rerun the test
module. The prior pre-run source review and this evidence review are distinct
from the author's execution.

## Scope and remaining gates

The negative cases cover joint/full protocol mismatch and missing feature,
destination preservation and cleanup. Positive controls cover a compatible full
pair, input-base repair and metadata restoration. Reuse uses shipped metadata,
not the current checkout; output changed by a synthetic packager is rechecked
after successful source preflight; plan remains non-mutating.

The active-pane check uses the selected published protocol/manifest hunks, not
execution or qualification of the coordinated active-pane implementation. The
gate checks manifest/metadata consistency, not the capabilities of actual
executables. General malformed metadata-schema validation, binary provenance
truthfulness and hostile/concurrent filesystem mutation are outside this fix.

All compatibility-test invocations request no archive. One serialization
method does exercise the real tar.gz path on inert synthetic fixture files;
the inode check uses an isolated stdlib Python subprocess. Neither is a real
portable release. No real builder, package.py, source resolver, metadata producer,
Cargo/Rust gate, native GUI, extension handshake, provider, installation or
release workflow was run by these tests. The gate is not a rollback solution
for archive failures and does not replace #142. No performance benefit is
established.

Final REPORT.md and README.md were read after the combined results. Their
scope, counts, alternative-patch instructions and outstanding qualification
gates are consistent with the inspected evidence. Source-input hashes must not
be presented as proof that every listed reference file was executed: the real
metadata producer was stubbed, and patch backup files are not test inputs.
Only the reviewed report, review, provenance/verification and patch artifacts
belong in the public package; raw logs and source copies remain excluded.
