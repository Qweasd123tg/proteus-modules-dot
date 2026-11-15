# Independent review: envelope policy prequalification

## Verdict

**Accepted as local preparatory evidence, not as active-workflow integration.**
No source-level or evidence-integrity blocker found for the report's stated
narrow scope. Do not apply the patch alone to the frozen strict workflow.
No publication, commits, workflow edits, live children, Rust or hosted CI were
performed by this review.

Reviewed patch SHA-256:
`068776c2f27f170ac954acd3c8c1e771cce0e4f12f0d46232bb4a7ed3e4d63e9`.
Fresh remote main remained `cbd9ec315f88f85708d26d47cc2193970a7c904b`.
An independently retrieved untruncated Git tree (5,386 entries) confirmed all
8 controller/test preimages and 21 supporting context files. The public hash
manifest also matched. No author-generated source identity was accepted
without comparison to that tree.

## Independent execution

The reviewer reconstructed the candidate from original source plus the exact
public patch, rather than executing an assumed after-directory. Verified
strict whitespace application, zero fuzz/no offsets, equality to intended
candidate, reverse and exact original bytes. Only one test method changes;
all 35 ordered test identities and all other AST nodes remain unchanged.

Using `python3 -B -I` with no escalation:

- Four original mocked/filesystem suites: 35 methods each, all PASS, no skips.
- Reconstructed strict candidate: 35 methods, all PASS, no skips.
- Existing verifier controls: 20 methods, all PASS.
- Actual unchanged `verify_ci.tests` accepted the new actual candidate log
  against the unchanged `EXPECTED.json`.
- Reconstructed all four authored controller mutations independently:
  original 35-method suites PASS; corresponding candidate suites FAIL only
  in the changed success method. No unexpected error or unrelated failure.
- Added an independent fifth fault injection: alter **only the serialized
  on-disk receipt** to `deadline_seconds=1800`, preserving the in-memory
  returned result. Original suite PASS; candidate FAIL at the explicit
  `receipt['deadline_seconds']` assertion for evidence/strict policies.

Repeated executions are not additional unique behavioral tests. These remain
mock-process tests with real bounded temporary filesystem work, not genuine
deadline waits, child termination, live fixtures or full strict integration.

## Freeze risk: now directly confirmed

Ran the actual unchanged `verify_ci.sources` function with the actual unchanged
`PUBLICATION.json`, using the original manifest's first five payloads in their
original order. Verified all five original payload hashes first, then replaced
only `ci/strict-fullturn/test_envelope.py` with the candidate bytes. The first
four inputs still matched, and the actual verifier failed exactly with:

`source mismatch: ci/strict-fullturn/test_envelope.py`

This is a bounded negative source-gate control, not a full positive source
verification: later manifest payloads were not materialized or evaluated.
The author's HOLD for standalone active application is necessary and correct.
No hash was rewritten or check waived. Migration must use a new explicit
active validation revision while preserving historical publication evidence.

## Findings and small clarifications

1. **Integration blocker, already disclosed:** a standalone active application
   fails the frozen source gate even though all local mocked tests pass.
   The preparation patch is useful only as evidence/part of the coordinated
   new-revision migration. Do not label it merge-ready or completed dedup.
2. **Non-blocking mutation-label precision:** the author's
   `receipt_hardcoded_1800` mutates the shared result dict, so its observed
   failures occur at the in-memory deadline assertion before checking disk.
   It is a real regression detector, but alone it did not independently
   demonstrate the persisted-receipt assertion. The review's disk-only
   mutation closes that narrow evidence gap without modifying the patch.
3. **Non-blocking diagnostic detail:** a deadline assertion inside the mocked
   `supervise` callback is caught by production `execute`'s `BaseException`
   handling. The monitor mutation therefore surfaces as a failed-status
   assertion, not the original timeout comparison traceback. The mismatch
   still reliably fails the test, confirmed by independent mutation runs.
   Moving call-argument checks outside the production exception boundary
   could improve diagnosis later; it is not required for the current result.
4. Confirmed the architectural warnings by source inspection: `MAX_PIPE`
   assignments target defining-module globals, AST-derived test expectations
   depend on the actual source path, package-local identity walks exclude the
   proposed shared owner, and workflow paths do not yet cover that owner.
   None of those integration gaps is solved by the narrow test-only patch.

The current report accurately avoids claims of live runtime PASS, shortened
CI time, safe test deletions or completed consolidation. New test frameworks,
globals proxies and policy unions are neither necessary nor recommended.

## Review artifacts

`CHECKS.json` records exact independent results and log hashes. Raw logs,
partial source trees and the local review driver are internal working
artifacts, not a proposed public source snapshot. A concise review/check
record may accompany the author's package if separately selected for delivery.
