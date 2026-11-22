# Move owned IDs through Desktop's Codex older-history overlap check

In an accepted older-history page, the archive already owns every incoming item. Check the existing (turn ID, item ID) tuple using those two strings, then move them back into the item for an insertion. This removes two discarded clones per input with nonempty IDs; it does not change the compound key, existing-row lookup, tool call-ID handling, or row lifetime. Same-item IDs in different turns remain distinct. Already-archived rows win even when the incoming payload differs, while duplicates inside the incoming page still use the existing upsert behavior.

Scope: only transcript/external.rs, one hunk in external_prepend. Stock Desktop b6a7ec2d8d7e486c8aba01291aa8c89774c4cded and cumulative sealed M150 plus the verified roster through #431 use the same proposed patch. Earlier #274 changes the adjacent construction of the independent window, not the overlap check; both forms are left intact. No changes to fetch/page sizes, cursor/anchor handling, routing, approval data, prune/eviction, byte budgets, transport or app-server calls.

## Scoped evidence

The real Codex history request asks for 50 items; the fixture projects 50 synthetic DTOs through the actual Codex projection including Unicode text, reasoning, user messages, file changes and tool arguments/results. It calls the actual transcript's external_prepend with an already populated archive. It is a fixture of the accepted page path, not a claim that every remote reply contains exactly 50 items.

| Input | Alloc/realloc requests | Aggregate requested bytes |
| --- | ---: | ---: |
| 50-item page, five overlap existing rows | 193 → 93 | 93,282 → 89,182 |
| 50-item page, all rows overlap | 102 → 2 | 34,924 → 30,824 |
| Duplicate, stale-row, Unicode, and missing ID controls | 24 → 12 | 8,887 → 8,796 |
| Empty page; page with only empty IDs | unchanged | unchanged |

Scope of counters: one external_prepend, outside input construction, snapshots, and teardown. The ordinary reduction is exactly 100 ID allocations and 4,100 bytes; successful rows and overlap skips both avoid the copies. Small and empty controls confirm the formula for nonempty strings only. Output ownership and retained-memory counts are unchanged; no timing or RSS claim.

Four fresh test artifacts (baseline/candidate on each tier), 9/9 each: six native external transcript tests and three focused fixture tests. Five complete snapshot byte streams compared equal across all four. Checks include the exact splice, row order, key allocation after insert/prune, stale mapping behavior, same-ID different turns, archive and intra-page duplicate behavior, timestamp preservation, text allocation identity on retained rows, tool arguments/results/call-ID, and complete retained-byte output. Fixture-visible projection and all transcript sources are copied byte-for-byte. No GPUI, app-server, remote connection, or tool execution.

Forward/reverse/whitespace/rustfmt clean on both source bases. Exact 125 dependency identities from existing warm Desktop closure (Proteus Contracts 7cbc7206f03fac130d05bed2844de275476fedc8; Serde JSON 1.0.152, preserve_order). One locked offline Cargo job, common build lock; unchanged 512/256 MiB floors and +200 MiB growth fence. Observed peak growth 5,860 KiB warm filesystem and 36,896 KiB temporary filesystem. A preliminary stock harness compile required passing turn.as_str() to accommodate its distinct historical projection signature; no test ran then and no product source changed. Sealed source and Cargo.lock rechecked after the successful run.
