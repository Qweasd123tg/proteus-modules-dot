# Envelope consolidation follow-up: qualify policy before sharing implementation

## Scope and verdict

Base: `Qweasd123tg/proteus-modules-dot` main
`cbd9ec315f88f85708d26d47cc2193970a7c904b` (merged #165), fetched and rechecked
unchanged in this pass. No upstream repository or dependency pin was changed.

The [#165 plan](https://github.com/Qweasd123tg/proteus-modules-dot/blob/cbd9ec315f88f85708d26d47cc2193970a7c904b/foundation/2026-11-15/bounded-simplification-batch/TEST-DEDUP-PLAN.md)
is directionally right. **Do not replace all four controller/test files with
thin wrappers yet.** Their active consumers have additional coupling that must
be migrated together. This pass supplies a tested, single-existing-test
preparatory candidate, not completed consolidation and not a production fix.

`strict-profile-wiring.patch` changes only the existing success/receipt test in
`ci/strict-fullturn/test_envelope.py`: +25/-12 lines. Its 35 exact named methods
remain 35. The success case now exercises all three existing local policies:
`core-skills=1800`, `evidence-spans=1500`, `strict-fullturn=2700`.

It verifies the exact local policy map, the actual deadline passed to the
mocked supervisor, profile identity, and deadline/profile fields in both the
returned result and on-disk receipt. The existing invocation, success,
snapshot-file and archive-byte assertions remain. No new suite, test runner,
controller class, production code or compatibility lane is introduced.

This closes a concrete pre-consolidation regression gap: the old strict suite
ran its success case under `core-skills`, not `strict-fullturn`. It did not prove
2700-second strict policy, nor that the monitor and persisted receipt agree.
The patch adds two subcases inside that existing method, not two new test
methods or two demonstrated production bugs.

## Executed evidence

These checks ran locally using `python3 -B -I`, without escalation or bypass:

- All four unchanged envelope suites: 35/35 each, zero skips. These are 140
  executions of largely duplicated definitions, not 140 distinct behaviors.
- Candidate strict suite: 35/35, zero skips; the expanded success method runs
  three policy subcases. All other AST nodes and ordered test identities match
  the baseline exactly.
- Existing strict prerequisite/verifier controls: 20/20, zero skips.
- Existing `verify_ci.tests('envelope', ...)` accepted the actual candidate log
  against unchanged `EXPECTED.json`; no weaker name/count gate substituted.
- Four targeted mutation controls below: every old suite invocation succeeded,
  every corresponding candidate invocation failed with 35 methods selected.
- Strict whitespace forward/reverse apply checks, actual zero-fuzz/no-offset
  apply, exact candidate comparison and exact baseline restoration passed.
- Eight controller/test preimages were Git-blob-verified against the fresh tree;
  supporting consumers/gates were retrieved at the same pinned commit.

| Mutation of strict controller | Original 35 | Candidate 35 |
| --- | --- | --- |
| strict deadline 2700 -> 1800 | PASS | FAIL |
| supervise receives hardcoded 1800 | PASS | FAIL (evidence + strict) |
| returned result declares hardcoded 1800 (also persisted) | PASS | FAIL at in-memory assertion (evidence + strict) |
| policy accidentally gains usage-attribution | PASS | FAIL |
| disk-only receipt deadline changed to 1800 (independent review) | PASS | FAIL at persisted-receipt assertion (evidence + strict) |

The mutations are authored fault injections in separate throwaway copies, not
reported defects in the current controller. The original map is correct.
Independent review reconstructed and repeated all four authored mutations, then
added the disk-only fifth control while preserving the returned in-memory
result. This separately demonstrates the persisted-receipt assertion. The
monitor callback assertion is caught by production `execute` exception handling,
so that mutation surfaces as a failed-status assertion rather than the original
timeout traceback; it still fails reliably. Repeated review executions are not
additional unique behavioral tests.

**NOT RUN:** real child/controller/live fixtures, Rust/Cargo/rustfmt,
Core/Modules/Desktop tests, full strict integration, hosted CI or benchmarks.
The mocked suites exercise bounded temporary filesystem operations but do not
prove descendant teardown or real elapsed deadline enforcement. No test was
deleted. No performance or CI-duration improvement is claimed.

## Additional integration constraints found

1. **A function re-export is not an equivalent controller module.** Both
   [usage live controls](https://github.com/Qweasd123tg/proteus-modules-dot/blob/cbd9ec315f88f85708d26d47cc2193970a7c904b/consumers/usage-attribution/ci/live_controls.py#L11-L27)
   and the byte-identical CAS live controls import their sibling module and
   assign `e.MAX_PIPE = 4096`. Python functions read the globals of their defining
   module. A wrapper re-exporting `supervise` while receiving that assignment
   will leave the actual owner at its 4 MiB limit, not the required 4 KiB control
   limit. Mock suites similarly patch attributes of their loaded controller.
   Consumers must import/patch the real owner, or use an explicit supported
   seam; do not add globals-proxy magic to disguise the mismatch.

2. **Thin test wrappers are incompatible with the present exact-name gates.**
   [usage verifier](https://github.com/Qweasd123tg/proteus-modules-dot/blob/cbd9ec315f88f85708d26d47cc2193970a7c904b/consumers/usage-attribution/ci/verify.py#L56-L70)
   derives `(test name, class)` by AST-parsing the sibling `test_envelope.py`,
   then requires exactly 35. CAS `gate_common.helper` does the same. A wrapper
   with no top-level test classes has an empty expected set, even if it executes
   the canonical suite. Change the invocation and the verified source path
   atomically; retain the exact canonical test identities/count and negative
   missing/extra/duplicate/status checks.

3. **Package-local source identity misses a new shared owner outside it.**
   Usage `contract.source_identity` walks its workspace plus its workflow; CAS
   walks correction-memory and evidence-spans plus its workflow. A controller
   or canonical test in `ci/resource-envelope-v1` is outside those inventories.
   Add explicit bounded shared inputs to both inner identities and each outer
   envelope `--input` closure, preserving source-change failure semantics.

4. **Triggers must follow the actual owner.** Strict, usage and CAS workflows
   currently watch their own directories, not `ci/resource-envelope-v1/**`.
   A shared-only edit must trigger all affected lanes. Core-skills already
   watches that owner directory. Keep Rust/integration lanes, pins and artifact
   destinations separate; shared Python code does not make their builds equal.

5. **Strict source freeze blocks even this small test patch if applied alone.**
   `verify_ci.sources` compares every payload to `PUBLICATION.json`.
   The baseline test SHA-256 is
   `aa6980d97dbaf469ae2dce9fbae99e0e23fd00dbcfca462b5bfb2a63b10237fe`;
   the candidate is
   `a8d4b8f2343e66ff5db9294eea6e161a4bb85970f18d0a0e36ec3647a6c90889`.
   The first matches the frozen manifest and the second does not. Independent
   review also ran the unchanged `verify_ci.sources` with the unchanged real
   manifest and its first five payloads: after four matching predecessors it
   rejected the candidate exactly with
   `source mismatch: ci/strict-fullturn/test_envelope.py`. This is a bounded
   negative gate control; later manifest payloads were not materialized or
   evaluated, and the full positive source gate is not claimed green.
   Preserve the old publication/evidence, introduce an explicit new active
   validation revision with full closure, and requalify that revision. Do not
   rewrite historical hashes or waive the gate to manufacture acceptance.

## Recommended bounded next step

Carry this one-method policy guard into the same reviewed active-revision
change as the real shared-owner migration, rather than publish a standalone
active test change that immediately fails the frozen source gate.

Use the existing resource-envelope implementation as the owner. Pass selected
policy/deadline explicitly, without a union of allowed profiles or mutable
shared policy global. Keep downstream entrypoints narrow; update live/mock
imports to the actual function owner, canonical suite invocation and verifier
AST paths, both source closures and workflow triggers together. Start by
retaining canonical suite execution in each affected lane, plus entrypoint
policy checks; remove repeated runs only after equal code/runtime/configuration
and their coverage are demonstrated. The 35 original invariants are retained.

Before accepting that migration: check isolated imports from existing cwd,
CLI permitted/rejected profiles and exit status; receipt and monitor deadlines;
shared-file mutation rejection at every source gate; all 35 canonical methods;
and the existing real live controls in their supported Linux environment. The
candidate here does not yet establish CLI allowlist behavior or those future
shared-import/hash-path properties.

## Publication status

Local review artifacts only. No commit, push, PR, workflow change or upstream
application was performed by this author/review pass. Independent review
accepted the exact patch as preparatory source/evidence only, with no blocking
finding in that scope. It independently verified the source tree identities,
reconstructed apply/reverse, repeated the mocked suites and exact-name gate,
and added the controls described above. The patch is not directly merge-ready
against the frozen active workflow; active integration remains outside this
acceptance.
