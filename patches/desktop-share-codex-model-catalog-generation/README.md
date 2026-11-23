# Share one Codex model catalog per provisioned workspace generation

Scope: Proteus Desktop, exact commit `f8cc40177ad3ab3d8ec36447a899332778f03268`. The workspace now owns the same immutable `Arc<[Model]>` that Codex chat bindings already use. Convert each returned nonempty catalog once; the original vector is moved, not deep cloned. Chat insertion and the destination workspace of a detached tab can share that snapshot. Replacing the workspace catalog does not alter earlier conversations or picker snapshots. Textually identical but independently returned catalogs are not interned.

The service still owns and uses its existing per-app-server model cache. `Boot` and `CodexService::models()` still return the same `Vec<Model>`; startup, create, and resume call ordering is unchanged. No change to model discovery, readiness, paging limits, errors, saved preferences, actual picker logic, widget callbacks, pending guards, or detachment/rehost logic.

## Focused verification

- Exact bytes/modes checked on the source preimage, actual forward application, and actual reverse. Pinned Rustfmt check passed for all three changed files on both arms.
- Rust 1.95.0 source lifts: 6 paired tests pass in debug and optimized builds. Real model/summary/open-request DTOs, real service cache and restore, boot application, insert/new/resume callbacks and ticket checks, and selector/menu expressions were exercised with inert service, window and event adapters. Tested order, duplicate rows/IDs, exact titles and efforts, busy/empty controls, stale or closed sessions, failed load, and old/moved/renewed snapshots.

Catalog handoff only, with 24 prepared synthetic models. Allocation requests and requested bytes, stock → candidate:

| Case | Requests | Requested bytes |
| --- | ---: | ---: |
| Install and four bound chats | 864 → 1 | 47,876 → 3,664 |
| One binding after install | 216 → 0 | 11,969 → 0 |
| Detach catalog capture/assignment | 215 → 0 | 8,305 → 0 |
| Empty binding | 1 → 0 | 16 → 0 |
| Nonempty install with no new binding | 0 → 1 | 0 → 3,664 |

The 24-model workspace and four bindings hold five distinct catalog payloads before and one after, excluding the unchanged service cache. Empty construction and replacement need no allocation with the tested Rust/Model layout. Nonempty install allocates one shared slice and releases the old vector buffer; the fixture requests 3,648 bytes of record storage plus a 16-byte Arc control block, and existing owned string/effort buffers are reused. That install cost is paid even if no binding is added. These are allocation requests and pointer/lifetime witnesses for the lifted operations, not app heap totals, RSS/PSS, startup, network, or wall-time measurements. No Cargo/GPUI or actual native/agent operation ran.
