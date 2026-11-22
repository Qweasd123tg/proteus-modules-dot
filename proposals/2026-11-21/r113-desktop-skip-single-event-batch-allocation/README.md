# Keep a single Codex chat event out of the heap batch vector

The live Codex chat already owns its first ready event. Apply that event at the start of the same UI update, then apply any additional ready events in FIFO order. Allocate a vector only when there is an additional event. The same 127 extra nonblocking receive attempts cap each batch at 128. Notification, the post-batch yield, rejection and disconnect stay exactly where they were.

One product hunk in src/ui/chat/codex/mod.rs, identical on exact upstream b6a7ec2d8d7e486c8aba01291aa8c89774c4cded and sealed M150 plus the full Desktop roster through #434. No change to Router, approvals, event projection, event or byte limits, GPUI scheduler, network, cursors, or archive.

## Scoped proof

Four fresh test artifacts: baseline/candidate on both tiers, all 14/14 (nine existing Router tests, five focused cases). The harness copies the exact Router, Types, Projection and local Codex client, uses actual async-channel 2.5.0, and mechanically lifts the exact native pump body and yield implementation. Its test recorder stands in only for GPUI's update/apply/notify boundary; it does not open a window, start the app-server or execute tools. The same four complete output byte records cover:

- Isolated streamed notifications, open/empty wait, retry notice remaining nonterminal, closed buffered completion and explicit final reason.
- A 128-ready batch plus a 129th arriving just after the first receive, proving the 127-attempt bound without growing the channel; FIFO next batch, default close reason, and exact update/yield boundaries.
- Rejected update returning without notify, yield, synthetic disconnect or consuming the remaining tail.
- An already closed channel holding a full 128-event tail, with no extra read beyond the cap, and the real disconnect reason only after the notified batch and its yield.

Allocation/reallocation requests and total requested bytes for the first successful ready poll, same on both tiers (real receiver, prebuilt/preallocated recorder, through exact yield; excludes event/fixture creation, waiting, closing and serialization):

| Events ready | Requests | Requested bytes |
| --- | ---: | ---: |
| 1 | 2 → 1 | 240 → 72 |
| 2 | 3 → 2 | 912 → 744 |
| 4 | 3 → 2 | 912 → 744 |
| 5 | 4 → 2 | 2,256 → 744 |
| 8 | 4 → 3 | 2,256 → 2,088 |
| 32 | 6 → 5 | 10,320 → 10,152 |
| 127 | 8 → 7 | 42,576 → 42,408 |
| 128 | 8 → 7 | 42,576 → 42,408 |

The single-event vector's one request disappears; the ready poll itself is not allocation-free. No retained capacity is introduced. The candidate holds one 168-byte Event by value until update; its other events remain heap-backed and there is no stack array. Reported size of the headless lifted async future is unchanged at 280 bytes on all four artifacts. This does not measure production GPUI stack depth, scheduler latency, or overall app RSS.

Both tiers passed SHA/source, forward/reverse, whitespace and rustfmt checks. One locked offline Cargo job under the shared build lock, existing 22-dependency warm closure, with the 512/256 MiB floors and +200 MiB growth guard. Maximum observed growth at fences: 3,780 KiB warm target filesystem and 36,708 KiB temporary filesystem. Sealed source and Cargo.lock rechecked after execution.
