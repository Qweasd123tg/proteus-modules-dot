# Choose a new terminal tab ID without rebuilding layouts

Desktop base: b6a7ec2d8d7e486c8aba01291aa8c89774c4cded. One common source.patch for exact stock and the exact selected tabs slice through Desktop #444. The production path previously cloned/merged saved window layouts and replayed all their tabs into another temporary layout to find one maximum numeric suffix. This patch scans the same saved live tab IDs directly, retaining the same manifest order, enablement, raw prefix, Rust u32 parsing, empty maximum, last + 1 and overflow behavior. Closed history and detached root identities are not live tabs. Persistence, navigation, actual terminal mounting, requested pane, Settings/auth checks, connection and other routing remain unchanged. The per-area pane vectors still exist.

## Focused evidence

- Stock Git plus sealed M150; 61 selected Desktop receipt hashes checked, including #444. The three production sources are unchanged across those predecessors. Only #440/#444 tabs hunks were added to the copied M150 tabs slice. Initial source inputs: 696 KiB; no full milestone materialization. Exact warm 11-dependency closure.
- Four fresh stock/cumulative baseline and candidate arms, 72 real tabs crate tests and 4 focused lifted tests in each (eight fresh executable artifacts). All 11 full comparator records match byte-for-byte, including the exact live ID union, saved layout bytes, terminal-number selection, ordered/disabled providers, and inert navigation/mount/show sequence. Ordinary one/two/three window layouts, loose/parked roots, live preview tabs, closed-only and detached-only controls, exact numeric spelling, Unicode and overflow are covered. Tests independently compare the old synthesized tab set and direct live tab set before measuring. The GPUI and extension boundary is modeled; the three method bodies and actual tabs crate are used as admitted.
- Scoped allocation/reallocation counts over 64 number lookups on each already-built layout:

| Saved windows | Cumulative requests, before → after | Cumulative requested bytes, before → after |
| --- | ---: | ---: |
| 1 (5 live IDs) | 3,776 → 448 | 268,928 → 7,872 |
| 2 (15 live IDs) | 12,800 → 640 | 560,448 → 14,016 |
| 3 (19 live IDs) | 16,768 → 832 | 774,272 → 20,160 |

Stock one/two/three requests were 4,672 → 448, 18,752 → 640, and 23,808 → 832. These count repeated lookups over fixed saved layouts, not repeatedly opening a terminal or whole UI/application latency, retained memory, RSS or native throughput. They include the unchanged output ID and residual pane views, but not fixture provisioning or the independent comparator. No PTY, terminal, real extension, app server, GUI or network was used.

The first admitted warm attempt stopped before any tests because a synthetic trace line used an invalid cfg predicate. The reviewed one-line fixture-only fix is in fixture-only-fix.diff; source.patch and verify.sh hashes did not change. The second separately admitted invocation passed once. The original failure and raw outputs remain separate from the proof packets.

Reproduce with verify.sh --prepare for source checks only, or --run only under separate sole slot admission. Warm one-job locked/offline build; 512 MiB target/staging, 256 MiB temp and 200 MiB growth guards, plus 32/8 MiB reserve before compile. cargo-provenance.json binds fresh artifact and input hashes; behavior.trace contains sanitized length/digests of raw matching outputs; work.log and evidence.log show scoped counters and fences.
