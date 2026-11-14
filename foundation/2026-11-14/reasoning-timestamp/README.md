# Late reasoning insertion can overwrite an unrelated transcript timestamp

## Status and scope

**P3 source-only custom-workflow/replay candidate.** Exact Core revision: `bcbda4435534a296c707a1daa250813d692f68e1`. This concerns derived display timestamps only, not canonical journal dates, message content, message ordering, or a demonstrated stock-provider incident. No project code, validator, tests, fixture or runtime was executed. This report is documentation only; no production source edit is included.

## Cause

[`TranscriptProjectionState::append_message`](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/app_server/transcript/journal.rs#L359-L391) records `start = rows.len()` before rendering. It then assigns the current message timestamp to every row in `rows[start..]`, with a tool-call-specific override.

New [`TranscriptRows::append_reasoning`](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/app_server/transcript/rows.rs#L48-L89) may insert a new reasoning row **before an already rendered answer**, shifting old rows into that suffix. Thus `start..` no longer identifies only newly appended rows. A shifted unrelated ordinary message receives the current message's first-occurrence timestamp.

This became reachable through the new late-reasoning insertion added in [Core commit 1936598](https://github.com/Proteus-harness/Proteus-core/commit/1936598be812bab6c6711f112d6fea61152cda83). Before the reasoning insertion change, this helper only appended rows in this path.

## Source-admissible construction for a future regression

1. Open one root turn with valid model request/response lifecycles. Record response A with ordinary Text part pA at t100, then response B with ordinary Text part pB at t200. IDs and exchanges are distinct.
2. Make the first history Append, revision 0 to 1, contain `[A(pA + new Conversation Reasoning rA), B(pB)]`. Existing pA/pB remain byte-identical; active message IDs are unique; rA has a fresh PartId.
3. [`committed_parts` visibility](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/app_server/transcript/journal/source.rs#L134-L157) makes both prior model responses visible in replay. They first render `[A@100, B@200]`.
4. Rendering history A sees only its new rA. `start=2`; insertion at index 0 produces `[reasoning-A, A, B]`. The timestamp loop touches index 2, now B, and sets its timestamp to t100.
5. Rendering history B has no unseen parts, so it does not restore B's timestamp. Expected display B@200 becomes B@100 by source tracing.

This is a proposed deterministic regression construction, **not an executed validated journal**. Independent review checked the source admission boundaries, but an actual strict `JournalProjection::build` pass remains a required gate.

An alternative source construction uses a compaction Replace retaining A/B and adding a fresh model-provenance reasoning part to A. It is not necessary for the minimal future test.

## Important rejected construction

Three ordinary history Appends `A -> B -> late A` are invalid: [`validate_active_history_ids`](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/session_journal/projection.rs#L695-L715) rejects duplicate active MessageIds. Do not use that simplified trace as runtime evidence.

The existing [`late_reasoning_on_an_old_item...` test](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/app_server/transcript/journal/append/tests.rs#L473-L505) is renderer-focused, not strict journal admission evidence. Its tail is a tool row, whose call-identity timestamp masks this particular failure. The append test helper explicitly permits non-validated renderer fixtures.

## Controls and correction direction

- Without late insertion, the old suffix ownership remains correct.
- If the reasoning row already exists, appending text does not shift rows.
- A tail belonging to A has the same expected timestamp and hides the error.
- A tail tool with known call date is protected by the explicit tool timestamp override.
- An unrelated ordinary B with a different first-occurrence date exposes the discrepancy.

Assign dates to actual newly created rows, rather than a length-based suffix that can include shifted rows. Options include passing date information into row creation or returning created-row identities/positions from rendering. Keep first-occurrence dates, inserted reasoning order and tool dates unchanged. Add a strict-valid replay regression with an unrelated non-tool tail and assert both full and incremental/fallback projection equivalence.

## Review and novelty limits

An independent source reviewer repeated the exact-SHA reads, confirmed the insertion/suffix mismatch, rejected the invalid repeated-Append example, and checked the source-admissible model-response/history sequence. No code was executed by either reviewer.

PR85 index and relevant published reports (`history-events`, `initial-persistence`, `round4-core`, `round3-framing`, `round3-models`) were reread, along with PR86-103 metadata and PR103's complete diff. Their described causes do not cover this new insertion/timestamp ownership mismatch. This is targeted deduplication, not a claim that every artifact in PR85 was reread. PR103's known child-event whitelist and dependency pin caveats are not counted as new findings.

## Contracts clarification

Core HEAD and Modules' pinned Core revision differ, but the complete Git subtrees are identical at `bcbda443` and `41bdfffa` for:

| Crate | Identical subtree SHA |
| --- | --- |
| proteus-contracts | `410ee383418b5417d45ab867a66e85e9b7ebff01` |
| proteus-module-protocol | `dafef8d56d2d9f97579b6be1552df7a88308b9f4` |
| proteus-module-sdk | `74e27f06f9d0c7aaa8fffe56e52b1d758ecc44a4` |
| proteus-process-host | `812c6cd2d479bb58603090f362c1e3051ef8e271` |

These identities were read from both exact-SHA Git trees. The differing pin is not itself evidence of wire incompatibility for this pair. The post-pin Core changes concern presentation/order and cache format; complete build/runtime compatibility remains untested. No additional substantial reasoning/replay defect was established in the inspected Pi changes.
