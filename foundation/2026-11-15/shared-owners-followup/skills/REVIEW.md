# Independent final shared-skills review

Reviewed final normalized `shared-skills.patch` SHA-256:
`571def00d3461f9a1a67e72b579f035cf8667b25713a7067f97d254cc0a46749`.
Reviewed validation driver SHA-256:
`a8cf23735609519ba73385da2fecaa7525b8bc8c4c11a90eadc030d74fdee696`.

This supersedes the earlier review of patch `a8236551…`: that candidate
omitted the new shared input group from the lock-only final post-check.
The final patch corrects that omission. No remaining source-level blocker
was found for publishing this as a bounded proposal/evidence package.
This is not approval to switch active CI without its affected gate or a
claim of compatibility with copying current-core-skills alone.

## Source and compatibility

The existing core-skills owner is reused; no new runner or copied compatibility
shim appears. Four removed current-lane scripts are owned in core-skills.
The probe, verifier and capture-control bytes match the removed copies. All
eleven verifier test-method ASTs are unchanged; only scenario selection is
parameterized. Current explicitly passes its own scenarios to both controls
and real verifier. Rust inputs, separate Core pins, eleven Core checks, lane
entrypoints and required Python control executions remain separate.

Current-core-skills is intentionally no longer a self-contained copied package.
Its four former private script paths disappear; both run and lock-only paths
now need the sibling shared owner. The README explains this tradeoff and the
run.sh header now says repository-layout gate, not standalone package gate.
If standalone package copying is a supported contract, active adoption must
wait for an explicit packaging decision that includes the owner. Publishing
the patch as a proposal does not resolve that contract or activate workflows.

The new four-file shared freeze is checked by the current source manifest
before gate execution and after the probe. The active CODE freeze contains
the shared-freeze manifest and checker. Current workflow path triggers and
resource-envelope inputs cover shared scripts. Historical validation and
source-pin artifacts are not amended to attest this revision.

The final lock-only post-resolution Python block now checks `shared_ci` as
well as harness and portable-module groups before writing passed status.
Only harness Cargo.lock is exempt, preserving the intended lock-resolution
workflow. The shared fields come from the prior source manifest; a changed
shared verifier no longer slips past the final check. This preserves the
existing bytes-based input-closure discipline, not stronger filesystem-object
identity, TOCTOU resistance or OS sandboxing.

Independently recomputed all 61 supplied original Git blob identities in the
initial review. For this final hash, repeated strict whitespace apply-check,
zero-fuzz/no-offset application to a new inert copy, whole materialized tree
equality, reverse-check/reverse and exact baseline restoration. Recomputed
both active CODE freezes and all four shared-file hashes successfully.

## Pre-run and actual evidence

The final driver delta was reviewed before execution. Added checks extract
the exact final Python heredoc from lock_only.sh and run only that read/hash
comparison body. Neither lock_only.sh, Cargo/rustup, Rust probe nor package
gate is executed. Remaining calls are the reviewed authored Python controls,
manifests/CLI fixtures, sha256sum, bash syntax parsing and probe --help.
Capture controls launch only bounded tiny Python child strings in their own
process groups; this is not full descendant-containment proof.

All final v2 stdout/stderr files and RESULTS.json were read or mechanically
checked against their expected diagnostics. They support **37/37 expected
outcomes: 27 zero exits and 10 intentional nonzero rejection exits**. These
are command outcomes, not 37 independent product tests. Eight suite logs
report **60 successful method executions = 15 unique Python methods × two
revisions × two compatibility lanes**, with their expected counts and OK,
without skips. This is 30 executions each for baseline and candidate.

New v2 post-check controls accept unchanged inputs and a harness Cargo.lock
change, and reject the mutated shared verifier with the exact shared_ci
assertion. Earlier negative controls still cover all four shared-file byte
mutations, one missing shared file, both wrong-pin directions, changed source
attestation, and excess scenario arguments. Synthetic own-pin reports pass.
Help equality and bash parsing do not execute the underlying product gate.

The reviewer additionally executed the exact old/new post-check Python slice
on a separate inert candidate copy. Four expected outcomes were observed:
unchanged candidate passed; the old post-check wrongly accepted a changed
shared verifier; the final check rejected it; changing only harness Cargo.lock
remained allowed. These four overlapping reviewer controls are not added to
the 37 author command outcomes or the 60 method executions.

Rust compilation, rustfmt, Cargo/build/package gate, lock resolution/fetch,
actual Core probe, full CI, resource-envelope runtime, native UI and
performance remain NOT RUN. Exact-head affected CI is still required before
active adoption; empty CI checks are not success. No publication was performed
by this reviewer.
