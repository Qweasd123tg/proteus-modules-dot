# Release already visited decoded history rows while building the same display prefix

One local ownership change and two-file patch to Core's cold display prefix builder. A scan gives the prefix callback an owned JournalRecord. The original caller borrowed each HistoryMutated message and retained all decoded payloads until the record completed. The candidate consumes that owned message vector, applies exactly the same identity updates per row, then drops the row's nested payload at the end of the iteration. The outer vector backing is still owned by the iterator through its last row.

Neither the original, separately validated canonical history, nor its ordered digests change. The visitor performs the same turn registration and, before processing each canonical message, extends the explicit committed-part set with the same parts. All message, part, tool call, exchange and visibility identity semantics are retained, including hidden/rehostable parts; compaction and tool-result binding metadata that were not indexed remain unindexed. The borrowed suffix path still evaluates all checks and does not mutate the queried sets. Nonmutation JournalRecords still use the borrowed visitor. Neither cache layout nor error/publication ordering changes.

The two production postimages are `f07a8b639365a3eec88bd5703734eaed3a164b6c` (view.rs) and `df9232b9686926c03492d4a4423156dba3825390` (view/prefix.rs), from Core `b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`. Only `source.patch` is production code; all probes, allocator tracking and hostile adapter cases are test-only. This visit is separate from #567 raw-line treatment and from R284's post-save canonical-model release. It is not a warm cache-hit, native worker-process, or Desktop startup change.

## Measurement limits

The measured overlap is inside the actual prefix visitor, after a physical staged record has been decoded. The ledger tags exact requested Layouts by base address, allocation generation and row position before either visitor starts. At each milestone it compares live nested allocations with the independently summed original suffix from that same record. The partial comparator excludes allocator bookkeeping; it never treats an allocation reusing a dropped address as a surviving row. The snapshot slot backing, raw staged file/line, retained canonical model and prefix membership tables are distinct owners.

The supplemental peak is a scoped, requested-Layout visit-only observation: the ledger includes still-live allocations from this scan at call entry and all current-thread allocation changes during the actual callback. It excludes work before the prefix scan (including different caller state), does not measure parsing peak or allocator usable size, and is not a platform/process RSS, full cold-session/repair peak or latency claim. Total visitor allocation counts and requested bytes must match. The largest deterministic effects concern already processed nested buffers at milestones, not the initial decode or end return where both arms have the same payload state.

## First observed outcomes

Both compiled feature graphs passed 60 paired cases, including 48 paired prefix scans each. Across all fixtures, each arm visited 167,186 decoded history-message rows in each layout. The native driver checks actual prepared cold display and repair entry points, projected and strict spools, deliberate no-spool reads, warm bypass, physical LF/decode/count faults and late cursor faults, cache writer faults, owned visibility and all prefix membership sets. The independent mixed visitor test also checks direct and packed codecs, repeated IDs, later provider records, retagged hidden parts, call/result/hosted/citation behavior, append/replace/checkpoint and a borrowed suffix. The tested cold display/repair callers make no cache write or digest after a failing prefix scan. The existing borrowed suffix identity logic is exercised separately; the end-to-end incremental publication workflow is not executed.

The first physical staged public shapes returned these results for both projected and strict readers. The numbers are original tagged **nested** owner bytes released in the candidate before the designated row, relative to stock at that same point.

| Four-repeat Cyrillic fixture | Halfway, default | Halfway, preserve_order | Three quarters, default | Three quarters, preserve_order |
|---|---:|---:|---:|---:|
| 5,000 history messages | 2,581,390 B | 2,981,390 B | 3,872,640 B | 4,472,640 B |
| 50,000 history messages | 25,838,890 B | 29,838,890 B | 38,763,890 B | 44,763,890 B |

The 50,000-row values cover 50,000 original nested allocations at halfway and 75,000 at three quarters. Stock retains them until callback exit. Candidate retains the original current and unread nested generations at each milestone and both arms retain the same per-record outer vector throughout. Allocated prefix visitor traffic was the same in both arms (835,956 B / 36 allocation events at 5k; 6,685,188 B / 45 at 50k). Originating shape, capacity and output remain unchanged.

For those physical visit-only windows the equal-baseline peak decreases by 487,236 B at 5k and 3,899,204 B at 50k, in either layout. Default measured 10,902,450 → 10,415,214 B at 5k and 97,539,578 → 93,640,374 B at 50k; preserve_order measured 12,030,130 → 11,542,894 B and 108,161,018 → 104,261,814 B. These are not parse, whole repair or process peaks. The direct unstaged control still passes original-owner and traffic/semantic checks; its first 5k measurement contains a 384-byte diagnostic trace baseline difference in each layout. We kept both first raw observations and draw no unstaged peak inference. Details are in `route-scope.md`.

`check_layout.py` rechecks the original raw JSONL independently of the Rust checks. `check_route.py` and `route-check-first.json` provide separate physical-stage, failure and request/trace checks against those same original raw files. `proof.py` verifies and recreates the source lifts, projected locked dependencies and both feature graphs. It stages with pinned local inputs and can rerun the offline native proof with `python3 proof.py --core CORE --archives ARCHIVES --rust-bin RUST_BIN --work NEW_EMPTY_DIR --action run`. The supplied proof was run in portable staging mode; actual native execution used the one verified offline build lane. No remote writes or synthetic-run worker/desktop performance claims.

## Raw receipt transport

The complete first-run JSONL receipts are stored as Base64-wrapped gzip. Decode them before invoking the checkers directly:

```sh
for mode in default preserve_order; do
  base64 -d "$mode.jsonl.gz.b64" | gzip -dc > "$mode.jsonl"
done
sha256sum -c RAW-SHA256SUMS
```
