# Independent pre-patch review

Verdict: proceed with the narrow per-view tab candidate. This addresses the already reported Git-view ownership defect; it is not a new finding or a complete native/session reset repair. Source review only: no Rust, tests, project execution, or historical reproduction was run.

## Decisive source facts

- `Git` is shared across the session's surfaces (`sdk/src/host/instances.rs`), whereas Desktop `DeclarativeView.tabs` belongs to each view and each tabs-node path. Desktop sends a tab action only when changing the native selection.
- Current Git `render(Panel)` resets the shared scalar when the addressed view has no shown tree. `action("tab")` changes that same scalar. `history_tab` uses it to decide whether to read history or return a loading placeholder. Consequently an unrelated panel can change another panel's content while its native selection stays History.
- A view-keyed map removes this ownership mismatch without copying log/graph caches. Passing `view` into `panel` and `history_tab`, defaulting missing entries to zero, and removing only that entry on an initially unshown render is sufficient for the selected invariant. Preserve the existing numeric conversion rather than adding unrelated validation.
- SDK close dispatch calls `closed` while the addressed view/context is still available, then removes shown/view routing. Cleaning the map there has the correct lifetime. A same-session re-render/rehost preserves the stable view and does not intrinsically invoke close. Existing `session_changed` reconstructs `Self::default()` with selected other preferences, so the proposed map naturally resets as the scalar did.

## Bounds and remaining limitations

Keep session-wide read caches shared and history loading behind the addressed view's History selection. A new map costs one string/key and integer per tab-action entry until close/reset; this is not a performance improvement claim. No eager history load, SDK registry, or protocol field is needed.

Do not claim this reconciles every Desktop/native selection with every extension reset. Native tab state is independently retained, and existing session-change/reset behavior remains outside this patch. Likewise the history-placeholder behavior for non-History values and rendering both tab trees remain unchanged. Other Git UI preferences remain shared deliberately; this is not per-view isolation of all panel state.

Proposed regression coverage should distinguish two live views with different selections, opening a third/default panel, addressed tab changes followed by sibling rendering, close/reopen cleanup, and unchanged session reset. Verify actual returned history content and read counts rather than only map entries. Seed `head_parent` for lazy-history read-count controls: panel rendering also calls `last_commit`, so a `/workspace/log` count without that control can conflate unrelated reads. Direct `panel` calls alone do not exercise the new/unshown reset or SDK close routing; state explicitly which layer each proposed test covers.

This is design approval, not approval of an unseen exact patch or test implementation. The source manifest contains 14 pinned inputs; the coordinator's Git identity verification is separate from this review's local source inspection. No Git write-operation behavior was evaluated.

## Exact candidate source review

Reviewed patch SHA256 `54037266588a304ffe8634ea1bfb22b2775e13bdb80e1fcacb4c266f4defc422`. Locally read candidate hashes:
- main.rs: `a86120e8ce783adfec92ffabbb6917e06f02f635164f29b0c415bbf76be93b6c`
- panel.rs: `5fa3baacbf6b215589bd218b8ac49ce5ff26f6a8a23e912d7873cfdea5d62829`
- tests.rs: `a7dbab534080740de34cd8f21ee15a80515d948a6382a83fd5dbbb763d91fc5c`

No blocking source issue found. The map uses the already imported HashMap, remains covered by Default/session reset, borrows the view only for lookups/removal, and owns a string only at addressed action insertion. The numeric conversion and History==1 eligibility remain unchanged. Both production builder signatures and eight existing direct test calls are updated consistently. No old scalar reference remains in the changed source. Closing an unrelated view only performs an idempotent map removal; shared caches are not invalidated.

The six proposed tests have plausible Rust borrow/lifetime shapes: the returned history reference borrows the caller's Value, and temporary roots live through their assertions. The existing recursive `find` visits a tab wrapper's children, so list assertions target actual History content rather than a state flag. Seeded `head_parent` matches the fixture's `abc1234`; a future refresh deadline prevents unrelated invalidation. Thus proposed zero/one log-read assertions have a coherent source explanation. The two-view cache test verifies lazy first load and reuse, not a performance measurement.

Important test limits are correctly explicit: helpers first invoke real Git.render, then inspect a second call to the same builder rather than capture the tree sent by Host.show. Close is a direct callback and its so-called reopened tree is a builder call, not a real SDK close/reopen sequence. The unshown stale entry is intentionally injected. Session reset checks the extension map, not native tab reconciliation. No same-session rehost/SDK Instances/GPUI integration is executed. The existing Fake uses loopback HTTP if run; these six additions and all existing Rust tests remain NOT COMPILED / NOT RUN in this review.

Verdict: the exact source candidate implements the selected per-view ownership repair without an observed source blocker. Native qualification remains outstanding; neither baseline-red nor candidate-green behavior has been observed here. The expanded 19-source identity catalog is coordinator evidence, not a claim that tests were run.

## Closing prose review

Accepted REPORT.md SHA256 `d1020114c1ebf143a92ca2644ee7414686ed2f3747cbcca5b9681362d577cb66` and README.md SHA256 `e76e805e1df26da7506bd90dde4fcf3584483b7bdb793833352c2403fc500ac1`. Patch remains `54037266588a304ffe8634ea1bfb22b2775e13bdb80e1fcacb4c266f4defc422`.

No blocking prose correction identified. The report correctly distinguishes session-instance state from process-global state; per-view selection from shared caches; source-inferred rehost behavior from unperformed native qualification; map entry removal from capacity/RSS reduction; and historical evidence from this source-only pass. The +16/−8 production change and eight caller adaptations match the reviewed diff. The six proposed controls remain explicitly NOT COMPILED / NOT RUN, with second-builder inspection and direct callback limitations stated. It does not claim all session/native reset coherence or PR146 integration was tested. Mechanical apply/integrity checks are coordinator evidence, not behavioral results. No additional execution was performed for this closing review.
