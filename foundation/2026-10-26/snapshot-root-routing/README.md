# Desktop snapshot-root routing: isolated correctness experiment

This portable two-patch bundle targets **Proteus-desktop `5748ac04f78eaffa1f4ea6102bd349ca61412e8d`**. It is not an upstream change, a production release, or a speed claim.

## Problem and narrowly scoped fix

An accepted session snapshot updates `Session.root_thread`, but the transcript's runtime routing baseline can remain unknown or retain the prior root. If the corresponding `TurnStarted` was already included in that snapshot, it may never be replayed. Child text can then enter an unknown-root transcript, or an old root can remain accepted after replacement/reconnection.

The fix updates the transcript routing baseline from every **accepted** snapshot, including snapshots whose visible suffix has not changed. A rootless snapshot restores the existing unknown-root behavior; it does not introduce a different routing contract. Cursor rejection, pagination, stable row keys and history preservation remain unchanged.

## Required composition order

1. Check out the exact source commit above.
2. Apply the existing, unchanged `performance/2026-10-26/desktop/desktop-pagination-retry.patch` (SHA256 `02c535b4ceb3431a7b2ee957dbb2d003cdf1fb6a8884c3c7c0c7387ecbe9ce98`).
3. Apply `0001-snapshot-routing-tests.patch`: behavior-preserving extraction of the production snapshot application into `Session::apply_snapshot`, plus six tests through that helper and the real SessionCursor/History/Transcript.
4. Run the named baseline regressions: require exactly five routing assertion failures and the rejected-snapshot control to pass.
5. Apply `0002-snapshot-routing-fix.patch`; require all six tests and the combined native `ui::chat::` pagination/snapshot suite to pass.

The expected-red baseline is **upstream + the existing pagination patch + the snapshot extraction/tests**, not pristine upstream. A compile error, empty filter, unrelated panic, setup failure or timeout is not evidence of the bug.

## Evidence and isolation

The dedicated workflow runs only in `Qweasd123tg/proteus-modules-dot`, on `ci/snapshot-root-routing-20261026`. Existing module sources, the previous performance bundle, and all previous workflows remain unchanged. No upstream branch, workflow, PR, release or deployment is modified. The publication is a draft PR; no merge or auto-merge is part of this experiment.

The runner verifies package SHA256 values and source Git blobs, applies patches with `git apply --check --index`, and records four source trees. The previous isolated pagination-flow runner executes before the new extraction because it intentionally checks the previous seven source hashes. It is not substituted for final combined native integration tests.

CI uses Rust 1.95.0, a fresh hosted runner, bounded build concurrency, an explicit shallow checkout of extension revision `3361fc1650c4ac6f167c3e48a0fba8980a5c9038`, command deadlines, and a 90-minute workflow ceiling. Evidence retains command identities, exit codes, complete observed test-name sets and only a 64 KiB log tail per command. Durations include compilation and are **not benchmarks**.

At initial publication, patches have in-memory composition/hash checks and source review only. No local build, Rust test or formatting command was run because the local machine is below its protected disk-space floor. Runtime claims require the exact remote commit's completed CI evidence. A successful targeted run still does not establish the full workspace gate, a real native window, portable delivery or measured performance.

Upstream licenses and authorship remain unchanged.
