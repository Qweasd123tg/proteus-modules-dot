# Avoid cloning no-store history just to detect a captured tool result

The two affected Core branches deep-cloned the current history to compare it with the result of capture. The existing, pinned HistoryCapture::record already says whether it inserted precisely one message. A successful insertion changes the length and makes the former comparison true. A non-inserting call leaves each message intact, so the new code uses its real derived same-value comparison for the non-inserting case.

That last check is intentional: an unchanged native typed message can carry an f32 ContextChunk score or an f64 hosted FileSearch score that is NaN. Its clone compares unequal under original PartialEq. A plain “insertion only” condition would incorrectly suppress an old revision bump. The candidate retains that result and checks native float bits independently of JSON, including signed zeros, infinities and quiet/signaling NaN. No scope or NaN semantics change is made to the unrelated checkpoint or full conversation operations.

Settling pending effects still evaluates every required capture even after an earlier insert. A later error still leaves the already inserted records/bindings, discards the rest of the drain and returns before incrementing the revision. The actual final recorder still awaits the external recorder under the same capture lock first, then checks attribution, locks effects/history, records under the same guards and retires matching pending effects on success. Persisted processing never runs the in-memory equality predicate; persisted settle still exits early. Atomic ordering, sequence, errors and order of existing operations remain in place.

Only source.patch is production code. Core b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14 checkpoint.rs has stock blob 5aa717381e5e51de30a4f281a888ada7220b790c and candidate 84b40b987bb3bbec833999c6dc0dd82fe35a4a5f. The lift runs the actual methods with real HistoryCapture, typed contracts, Tokio mutexes and an external recorder fixture. The stateful recorder fixture's underlying remote transport is not a native Worker; see route-scope.md.

## Measurement boundary

The current-thread Layout ledger starts at the genuine history lock acquisition in each affected branch and stops after the scope's own cleanup, preserving every original allocation/retirement event in that window. It counts successful allocate/zeroed requests and a realloc as one old-size free and one new-size allocation. It does not measure retained allocator pages, process/overall peak, CPU/wall time, the outer future, cold open/first startup, OS RSS/PSS or a deployed Worker. Partially drained inputs allocated before the scope may result in a negative net count; compare exact requested bytes/counts with an independent clone of the same original history, not with process memory. Validated new captured rows still use the same insertion allocation behavior.

The earlier unshipped insertion-only proposal was held because it intentionally changed the no-insert NaN outcome. This narrower replacement preserves that behavior and must not be combined with the earlier proposal.

## First observed paired results

Both compiles passed 86 native route pairs and one independent all-variant typed equality control per layout, including 62 pairs with instrumented history-lock scopes. For both no-store entry points, the stock-vs-candidate requested-Layout difference is exactly the independently measured clone of the identical history, including free events and final net state.

| Public synthetic history with no declared result to insert | Default original clone bytes removed | preserve_order bytes removed | Allocations removed |
|---|---:|---:|---:|
| 5,000 text messages | 3,403,890 | 3,803,890 | 10,001 |
| 50,000 text messages | 34,088,890 | 38,088,890 | 100,001 |

In the measured no-insert scopes the candidate adds zero requested allocations. Bound examples add the genuine tool-binding owner to the original history; their 50k clone sizes avoided are 34,091,475 B in default and 38,090,831 B in preserve_order. Those values also match the late-error batch with a committed earlier suffix row but no revision increment. Candidate allocations needed for inserter output were not removed or counted as savings. Persisted arms retained identical scoped allocation traffic and revision behavior.

The route tests verify real declared binding ownership, requested/resolved callbacks, exact observable suffix order despite reverse completion, no bound/no insertion, exact scope and pending retirement, raw/final ordering, wrong attribution, empty/persisted bypass with locks blocked, failure and terminal drain behavior with exact error, pending/cancellation before multiple gates and successful retries, SeqCst wrapping and old NaN/finite outcomes. The direct equality witness covers all ContentPart variants (including both hosted tool shapes), negative/positive zero, finite/infinite values, signed quiet/signaling NaNs, complex metadata and non-UTF-8 path bytes using the pinned concrete DTOs. It checks actual native bits of original and cloned scored data, rather than relying on JSON to carry NaN. There is no broader Worker/installed app performance claim.

GATES.md records predeclared claims and constraints. Both original raw files and check_layout.py are shipped with matching summaries. The portable stage verified 145 pinned Core source files, 152 exact locked archives and 8,573 archive members and the exact generated proof; recorded execution used the single verified offline build lane. For an offline replay with the required pinned local inputs, run python3 proof.py --core CORE --archives ARCHIVES --rust-bin RUST_BIN --work NEW_EMPTY_DIR --action run. No changes were published.

## Raw receipt transport

The original JSONL receipts are stored as Base64-wrapped gzip. Decode them before running the receipt checkers directly:

```sh
for mode in default preserve_order; do
  base64 -d "$mode.jsonl.gz.b64" | gzip -dc > "$mode.jsonl"
done
sha256sum -c RAW-SHA256SUMS
```
