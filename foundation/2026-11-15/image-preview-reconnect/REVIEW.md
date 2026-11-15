# Independent source review

The independent reviewer inspected the selected policy, pinned baseline, exact candidate diff and proposed tests. No candidate code was edited or executed by the reviewer.

Reviewed patch SHA256: `d97bde7154b567b07d53f3ac71c3f0d235408f586ab283a27bb1151eee55fff8`.

## Design and exact-diff conclusions

- A boolean credit is a minimal state rule for both failure/reconnect orderings; clearing only already-Failed slots would miss an old attempt's later failure.
- The production key/ticket/Loading guard remains before cache insertion and credit consumption.
- Success and flagged/unflagged failure transitions agree with the chosen policy. Fresh production fetch slots start without a credit.
- Queue admission, reservations and completion release are unchanged.
- Scheduled-before work includes queued attempts. Reconnects before a completion coalesce; duplicate Connected without a link error does not grant a credit.
- No source blocker was found. The recommendation is an uncompiled source proposal, not production approval.

## Verification gap resolved during review

The first exact review requested direct constructor/config evidence rather than inferring no-HTTP behavior solely from the existing test pattern. Exact pinned `mod.rs` and `actions.rs` were then added and checked against the Git tree. The reviewer confirmed that `Chat::base` stores API=None, `supports_core` is false, and `load_config` returns before a request; `Chat::call` also checks API before spawn/job. This is static path evidence, not observation of a test run.

## Test limitations retained

All five proposed tests are NOT COMPILED / NOT RUN. The replacement admission is manually modeled, the stale result is checked via the existing predicate rather than through the asynchronous production closure, and native row redraw is not exercised. The success fixture has no real bitmap. No HTTP, decode, real attachment or project runtime was executed.

## Final prose review

The reviewer found no blocking prose issue. Scope and +187/-7 agree with the diff; the scheduled-before policy, additional costs, five NOT RUN controls and absence of native recovery proof are explicit. The metadata-ordering assertion in the text checker is disclosed separately and not presented as a candidate change.

Reviewed document SHA256 values:

- REPORT.md: `55fb3e844017fcb11b7151d27dd12101040d188ca6c828e82528ea377fa980bb`
- DESIGN-DECISION.md: `1009a233890e5411cd25817190249d0aeac8ed8298928205d45978a4aa03ea09`
- README.md: `399baa562399f16fde9806dbbd4d67c07abb902580211dbe4841432d04b8f542`
