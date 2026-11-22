# Count Desktop panes without building a scratch vector

The tab-bar's closeability check only needs a scalar count. It used to ask for the entire ordered vector of pane references and immediately discard it. Count pane leaves directly instead. The recursive walk still sees every leaf in every child split, including empty panes, and empty splits contribute zero. The other ordered-list consumers still get the same vector as before.

Single hunk in crates/tabs/src/layout.rs on exact Desktop b6a7ec2d8d7e486c8aba01291aa8c89774c4cded and sealed M150 through #438. The tab controls build their menu state on every render, even when the menu is closed. The existing can_close result, active pane and earlier weighted placeholder rules, persisted layout, geometry, drag, lock and menu implementation are unchanged. Earlier #267 changes neighboring pane lookups, so overall controls on pinned stock still have an independent lookup allocation after this patch.

## Focused work comparison

Aggregate allocation/reallocation requests and requested bytes, exact cumulatively patched base through #438 versus proposed change:

| Fixture | Scalar count requests / bytes | Tab-bar closeability sweep requests / bytes |
| --- | ---: | ---: |
| One populated pane | 1 / 32 → 0 / 0 | 1 / 32 → 0 / 0 |
| Two populated panes | 1 / 32 → 0 / 0 | 2 / 64 → 0 / 0 |
| 2×2 populated grid | 1 / 32 → 0 / 0 | 4 / 128 → 0 / 0 |
| Twelve populated panes | 3 / 224 → 0 / 0 | 36 / 2,688 → 0 / 0 |
| Split with a locked pane and empty room-holder | 1 / 32 → 0 / 0 | 3 / 96 → 1 / 32 |
| Empty split, in-memory control | 0 / 0 unchanged | 0 / 0 unchanged |

One closeability expression per existing pane, not a full toolbar render. The candidate removes precisely the cost of the scalar count on every arm; other allocations stay in place. For example, pinned stock one populated pane is 2 / 64 → 1 / 32, and pinned stock grid is 8 / 256 → 4 / 128. Inputs and record buffers are built outside the counters. Requested bytes are aggregate requested sizes, not simultaneously live bytes. No FPS, timing, or overall app-memory claim.

## Parity and binding

Four exact arms, eight fresh artifacts: 72/72 native pure-state tabs crate tests plus 3/3 focused tests on each arm. The fixture mechanically lifts the exact product tab-bar closeability expression; it does not emulate menu painting. Actual open/split/lock methods produced the ordinary and reserved-room layouts. Ten complete byte records matched, including ordered IDs, closeability/missing-ID behavior, valid layout geometry bits, and saved layouts. In-memory locked-empty, invalid fixed-empty, empty split and nested duplicate-ID controls kept their original results without changing rules for saved layout validation.

Forward/reverse/whitespace/rustfmt passed on both tiers. The exact tabs crate uses the existing 11-external-dependency locked subset of the pinned Desktop Cargo.lock. Warm target, single offline locked job and the common lock; keep 512/256 MiB floors and +200 MiB guard. Peak observations at fences were +17,048 KiB target and +37,120 KiB temporary. Sealed source and lock rechecked unchanged after. No native GUI, app-server, or remote action.
