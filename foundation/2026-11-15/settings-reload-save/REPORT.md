# Settings reload: one acceptance boundary for profile snapshots

Status: source-only candidate for the existing PR85 `desktop-settings` Reload × Save family. No new runtime finding, compilation or production readiness is asserted. No upstream, live profile, native application or external provider was changed or run.

## Applicability and problem

Desktop main remains `7eaf70c67dabba8595d98029c875ffc3f59209ad`. The affected `src/ui/settings/mod.rs` and `save.rs` are byte-identical to their historical `75bf201764278eac4b50d156650edcf1429101ff` versions underlying the prior report. Delivery main is `06a148dcf9668a6f598179d02aed0df503c37db0` after PR135. The old report's reproduction and test counts were not rerun here.

The known failure is a delayed reload returning after a successful Save. Successful acceptance makes the draft clean again, so the read's dirty-only guard accepts an older snapshot, resets the draft/baseline, and can put an already saved old value into the next whole-slot save request. Current source still has this guard.

The fundamental distinction is between local edits and accepted profile state. `edit_revision` protects newer editor buffers across an ACK; it is not a sequence of accepted snapshots. Both `accept` and the newer-edit branch of `accept_save` can update baseline/state without changing it. Capturing only edit_revision at read dispatch is therefore insufficient as a common barrier, notably when a catalog ACK changes the baseline without a local editor change. The Reload button does not currently exclude catalogs.busy, although starting a catalog action during an existing reload is guarded. This is a source-level coverage observation, not a newly executed catalog race reproduction.

## Candidate invariant

Every accepted profile snapshot, including a value-equal snapshot and either Save ACK branch, advances one local profile_revision. A pending profile read may not publish success or failure after that revision changes. A successful read also may not replace raw/local edits made since dispatch, even when the parsed draft is clean. The existing dirty guard is retained for a read that started already dirty.

Implementation:

- A private `accept_baseline(snapshot)` owns the baseline + Ready-state assignment and advances profile_revision. `accept` calls it before resetting the draft/editors; the newer-edit branch of `accept_save` calls it without resetting newer local state.
- `edit_revision` is unchanged by snapshot acceptance. Existing manual/catalog ACK classification and conservative reconciliation retain their previous meaning.
- `load` captures both revisions. Its production callback calls the extracted `finish_load`, which applies the acceptance checks and clears reloading/notifies as before.
- A guard inside `load` refuses another request while reloading is true. Every admitted read, including initial loading, sets that existing flag. This provides a real single-in-flight invariant rather than relying on a rendered disabled button. No third request counter or generic async framework is added.
- Save eligibility is unchanged: the patch does not add `!reloading` to can_save. A successful Save can continue while a read is pending; the older read is later ignored instead of undoing it.

The local revision is not a server revision, ETag, timestamp or global ordering guarantee. It records accepted events, not value inequality, and does not claim to infer when a remote snapshot was taken.

## Simplification and boundaries

There were two assignments each to baseline and Ready-state across mod.rs/save.rs; the candidate has one of each in the shared acceptance method. This is the useful reduction: every accepted snapshot goes through the same invalidation boundary, rather than attaching a dirty/status check to each competing workflow. The patch has four changed paths: mod.rs +25 net lines, save.rs −1, one test declaration and a new test module. Total production code grows by 24 lines; no speed or overall LOC reduction is claimed.

The change intentionally conservatively rejects a read after any intervening raw edit, including edit-then-undo. It follows the existing "edits made while the profile was read win" rule rather than treating final value equality as freshness. Another explicit Reload can fetch current remote state. Similarly, a read started before a newly accepted snapshot is discarded even if its payload happens to equal or be more recent than that snapshot; there is no server-side revision to establish that ordering. Stale read errors no longer replace newer accepted feedback, while a current read error retains its existing handling.

The single-flight guard changes only private request admission, not a new visible control. Initial Loading already shows a loading page rather than the normal save bar. Reload continues showing its current snapshot while pending. No request cancellation or new networking behavior is introduced; the pending read finishes and its result may be ignored.

History's detached reads have separate lifecycle questions. This proposal does not reuse profile_revision for history or claim latest-request-wins for that stream. Doing so naively could discard an initial history read merely because the accompanying profile read was accepted. Addons already retain their request task and are likewise unchanged. Cross-window writers, server-side compare-and-swap, profile migration, process/runtime semantics, and unrelated security paths are outside scope.

## Proposed tests, not executed results

The eight new `audit_tests/reload.rs` test functions use the existing native-test context and real SettingsView/Draft methods. A small test helper marks a pending read and captures revisions; completion order is explicitly controlled through the same finish_load method called by production. No HTTP request or runtime is dispatched by these tests.

1. Old read after manual Save cannot restore a=1; a later b-only edit still produces the expected whole-slot `{a:2,b:2}` outgoing request. can_save remains true during the modeled pending read.
2. Catalog acceptance invalidates the old read without changing edit_revision or erasing the accepted addon delta.
3. Value-equal ACKs advance profile_revision in both same-revision and newer-edit branches; an older error cannot replace accepted feedback, and newer edits remain intact.
4. Current clean-read success and current errors retain their normal acceptance/failure behavior.
5. Both valid same-value raw JSON and invalid raw input retain editor identity/text against a delayed successful read.
6. Edit-then-discard cannot make an older read authoritative merely because dirty becomes false.
7. A read that starts already dirty still respects the existing dirty guard, even without an intervening revision change.
8. Calling load during an active read returns before changing state or reaching the no-profile branch. This is a direct guard check, not a network-concurrency test.

All eight are proposed Rust tests, NOT RUN. Their methods and expectations were independently source-reviewed. These are not passing tests, a new HTTP reproduction, real click ordering, or proof of native scheduling. Existing ACK/raw-editor tests remain unchanged.

## Actual verification and integration gates

- Thirteen Desktop baseline files are pinned by commit, Git blob and SHA256. One contract-reference file is separately verified at the actual Desktop Cargo pin, Core `41bdfffa6e70228278b4abc758b7f81a12672f35`, rather than substituting current Core main.
- Strict `git apply --check --whitespace=error`, actual patch application in an isolated staging copy, and exact candidate byte comparison succeeded. SOURCE-CHECKS.json records these file-level operations.
- The exact published PR134 and PR135 patch blobs were matched against the local patches. Applying candidate → 134 → 135 and 135 → 134 → candidate produced identical final source bytes. This qualifies patch mechanics only, not compiled composition or behavior.
- `rustc`, `cargo` and `rustfmt` were unavailable in the selected PATH. Compilation, formatter, the eight proposed tests, native UI/HTTP scheduling, real persistence and runtime checks were NOT RUN. Python was used only for file/hash/diff bookkeeping, not a replacement behavioral model.

Before production qualification: run formatter and focused Desktop settings tests with its actual dependency pin; exercise real delayed GET/Save and GET/catalog-ACK completion in both orders, current/stale failures, same-value/invalid raw edits and repeated reload admission; verify the next actual save/readback does not undo the accepted value. PR134/135 remain uncompiled proposals themselves, not prerequisites claimed to be validated runtime fixes.

Patch SHA256: `d748b20126f3f23b6f8f0828092570e356542eb18ced66b08fa0fcb393131f2a`. SOURCE-REVIEW.md records the independent exact-patch review; INDEPENDENT-REVIEW.md records the architecture review. This is one bounded acceptance-invariant proposal, not closure of all settings asynchronous-state issues.
