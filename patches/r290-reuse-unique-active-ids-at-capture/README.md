# Reuse an already valid unique index after one independent captured result

The strict result binding inserts exactly one canonical message at its actual binding-order position. The old active-ID check then rebuilt both message and part uniqueness sets over the whole history. The patch reuses that index only when it already exists, its Arc is genuinely unique, the actual inserted row has exactly one part, and both newly inserted identities are absent from the respective original sets. It registers those two facts. The canonical result still belongs to history and the exact known-part stability check still follows.

On a shared, missing or unknown index, unexpected row shape or any identity hit, the candidate uses the original ordered full check. The full check may legitimately name an older row after the captured row as the location where a duplicate part encounters its second occurrence. A collision is never reported by the fast path. The existing full-check invalidation, exact diagnostics, COW behavior, subsequent history appends/replaces, actual captured result order, revision/interruption and partial state/late known-part error ordering are preserved.

The target changes exactly the successes of real ToolResultRecorded and TurnSettled capture in the pinned contracts/semantics implementation. It is not an optimization of pure texts, no-store live recorder, unbound/late invalid captures, or general history validation.

## Applying the patch

Source composition is exact and independent of the native benchmark, which used the standalone patch. Use **one** of these R290 alternatives:

* For the pinned standalone base (Core b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14, original active_ids.rs ff2f6cc2bdf30ee014398133c4800955716c5b9f and facts.rs 79d35068789ee30c0ccac1641b828b3865c0b2ef), use source.patch. Resulting blobs are active_ids.rs 9ce2bf4cd39c9c22880409a7c663f29415f5ec2a and facts.rs 1eefa56e733cda007c6c6351a9038ae6197fdcb5.
* If exact #592 is already applied, use r290-after-592.patch instead of source.patch.
* If standalone R290 was applied first and #592 is desired, 592-after-r290.patch is the verified reverse-order counterpart of #592, not another copy of R290.

The direct unchanged base-context hunks overlap textually; do not fuzz or force-apply them. Both context-pinned sequences apply and reverse strictly and lead to the identical combined exact facts.rs ef8c636c43e03fbea4b189420add0f29d78ea7b2 and active_ids.rs 9ce2bf4cd39c9c22880409a7c663f29415f5ec2a. No runtime result is attributed to the combination.

## Measurement boundary

The pinned complete semantics/contracts and real im dependency exercise strict validation on physical synthetic JSONL and genuine typed records. Allocation observation counts exact current-thread requested Layouts and actual scanned row/part attempts within the original full uniqueness check versus the real narrow reuse. Test-only scope setup, precondition fixture construction and allocations outside the check are distinct. Independent history capture clones/new rows and known-part checks are not savings. The scope is not CPU/wall time, installed Worker/Desktop, process/RSS/PSS, complete validation or cold launch peak.

## First observed outcome

Both builds passed 53 paired strict sequenced cases and three separately labeled direct adversarial shape/Weak cases. In each layout, 53 actual bound-capture active-ID checks were measured, 33 of them taking the narrow candidate route. The independent state checks compare typed history and memberships and preserve the actual old-row duplicate-part diagnostic and late known-part error ordering.

| Genuine unique-index final capture | Requested allocations removed | Requested bytes removed | Old full row attempts avoided |
|---|---:|---:|---:|
| 5,000 public-shaped input messages plus tool binding/lifecycle and fixture rows | 25 | 557,416 | 5,003–5,004 |
| 50,000 public-shaped input messages plus tool binding/lifecycle and fixture rows | 31 | 4,456,904 | 50,003–50,004 |

Both layouts agree. On these exact fixtures candidate lookup/registration kept the same Arc, scanned no old rows/parts and requested zero allocation in the active-ID scope. Other necessary result-capture work and history/stability input ownership are unchanged; a different legitimate set capacity may still require growth. Both true middle insertion and tail-at-checkpoint cases qualify. A genuinely shared final index still performs the same complete original validation. A shared two-result settlement still rebuilds the first index, then reuses it only when it truly becomes unique on the subsequent capture. An already unique two-result settlement avoids both scoped rebuilds (8,913,808 cumulative requested bytes in the 50,000-row fixture, not simultaneous resident memory).

The native matrix separately reproduces lookup-before-fallback collisions, a duplicate part diagnosed at the old later row, message-before-part error order, an absent index following actual rejection, post-active known-part failures, duplicate/failing/unbound captures, saturated revisions, cancellation/interruption and subsequent append/replace validations. The direct controls exercise an unknown index, a non-singleton row and a held Weak despite one strong owner; all use the unchanged full ordered check. They are not asserted to be valid newly captured shapes. Exact context-pinned source-only #592 composition is recorded in composition-receipt.json. No native measurements of the composed route are asserted.

The first raw data and independent checkers are included. Portable staging verified 139 pinned source donors, 152 exact locked archives and 8,573 archive members with the exact generated proof and both feature layouts. For an offline replay with pinned inputs, use python3 proof.py --core CORE --archives ARCHIVES --rust-bin RUST_BIN --work NEW_EMPTY_DIR --action run. The portable recipe was staged, and native runs used the single verified offline build lane. Nothing was deployed or published.

## Raw receipt transport

The original JSONL receipts are stored as Base64-wrapped gzip. Decode them before running the receipt checkers directly:

```sh
for mode in default preserve_order; do
  base64 -d "$mode.jsonl.gz.b64" | gzip -dc > "$mode.jsonl"
done
sha256sum -c RAW-SHA256SUMS
```
