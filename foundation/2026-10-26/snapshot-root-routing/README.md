# Desktop snapshot-root routing: isolated correctness experiment

This portable two-patch bundle now targets **Proteus-desktop `2bf38f67055f10f5ed0fd225399ba77d84756ba1`**. It is not an upstream write, a production release, or a speed claim. Completed results for the previous `5748ac...` base are preserved separately and do not establish this new base.

## Problem and narrowly scoped fix

An accepted session snapshot updates `Session.root_thread`, but the transcript's runtime routing baseline can remain unknown or retain the prior root. If the corresponding `TurnStarted` was already included in that snapshot, it may never be replayed. Child text can then enter an unknown-root transcript, or an old root can remain accepted after replacement/reconnection.

The fix updates the transcript routing baseline from every **accepted** snapshot, including snapshots whose visible suffix has not changed. A rootless snapshot restores the existing unknown-root behavior; it does not introduce a different routing contract. Cursor rejection, pagination, stable row keys and history preservation remain unchanged.

## Required composition order

1. Check out the exact current source commit above.
2. Apply the existing, unchanged `performance/2026-10-26/desktop/desktop-pagination-retry.patch` (SHA256 `02c535b4ceb3431a7b2ee957dbb2d003cdf1fb6a8884c3c7c0c7387ecbe9ce98`).
3. Apply unchanged `0001-snapshot-routing-tests.patch`: behavior-preserving extraction of the production snapshot application into `Session::apply_snapshot`, plus six tests through that helper and the real SessionCursor/History/Transcript.
4. Run the named baseline regressions: require exactly five routing assertion failures and the rejected-snapshot control to pass.
5. Apply unchanged `0002-snapshot-routing-fix.patch`; require all six tests and the combined native `ui::chat::` pagination/snapshot suite to pass.
6. Run the current upstream's three focused `ui::extensions::declarative::view::preparation` tests as an additional integration gate for the newly changed upstream module.

The expected-red baseline is **current upstream + the existing pagination patch + the snapshot extraction/tests**, not pristine upstream. A compile error, empty filter, unrelated panic, setup failure or timeout is not evidence of the routing bug.

## Current-base compatibility checks

All three patch byte streams are unchanged. The actual current-base source bytes were fetched and every unified hunk/context/count checked in memory, not merely accepted because file paths looked unchanged. All changed-source Git blobs still match the reviewed composition. The complete Git trees were recomputed from all 618 current source blobs and are enforced by the runner:

| Stage | Expected Git tree |
| --- | --- |
| Upstream | `a3f43472fb25c1d760210f320fa847d3d77f0a95` |
| Pagination prerequisite | `3a4eb4c331c0b704c746e8cda5d2ea649c757ccd` |
| Snapshot extraction/tests | `fedf7e1678095e33ad18d768cf9b93da7d76b291` |
| Fixed composition | `09b082d4c76ecc88603d9b8e13f6d61578a8ec77` |

Cargo.toml and Cargo.lock still pin contracts to `f2ef701ef53c7bd45ba3acf58360fa1e77ddfb60`. Current repositories.json pins harness `63454d4e8b1e4e6b26d088fce2a17d46f30390ae`, modules `0d9c5fd18f04e6e3a083351678065c5f72966792`, and extensions `3361fc1650c4ac6f167c3e48a0fba8980a5c9038`. The runner verifies the actual configuration blobs, parsed repository/Cargo identities and lock source. This focused Desktop run does not execute the whole new Core/Modules runtime.

The old isolated helper intentionally pins the old source HEAD and is left untouched. This bundle's new `run_flow_tests.py` checks the current manifest's source commit and pagination-stage blobs, then compiles the same production `history_flow.rs` for its four named tests. It does not simulate or replace production logic.

## Preserved historical result

[historical/desktop-5748ac-evidence.json](historical/desktop-5748ac-evidence.json) preserves the independently audited old-base result at bundle `da41057093250447af3c8dde7ce0846fb110399b`, [run 40415824766](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40415824766): five exact routing failures plus one control before the fix, six snapshot passes after it, 32 native chat passes, four isolated pagination-flow passes, and formatting success. Exact archive/result hashes and all four historical source trees are recorded. These results are **not relabeled as current-base results**.

## Evidence and isolation

The dedicated workflow runs only in `Qweasd123tg/proteus-modules-dot`, on `ci/snapshot-root-routing-20261026`. Existing module sources, the previous performance bundle, and previous unrelated workflows remain unchanged. No upstream branch, workflow, PR, release or deployment is modified. This is a draft PR; no merge or auto-merge is part of the experiment.

The runner verifies package SHA256 values, complete source trees and Git blobs, and applies patches with `git apply --check --index`. CI uses Rust 1.95.0, fresh hosted source trees, bounded build concurrency, the explicit pinned extension checkout, command deadlines, and a 90-minute workflow ceiling. Evidence retains command identities, exit codes, complete observed test-name sets and a 64 KiB log tail per command. Durations include compilation and are **not benchmarks**.

At publication of the current-base update, composition and pins have static checks only; fresh current-base runtime validation is pending. No local build, Rust test or formatting command was run because the local machine is below its protected disk-space floor. Runtime claims require the exact new bundle commit's completed CI evidence. A successful targeted run still does not establish the full workspace gate, a real native window, portable delivery or measured performance.

Upstream licenses and authorship remain unchanged.
