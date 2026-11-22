# Reuse the last accepted Desktop extension popup tree

One Desktop production patch. The same two-file change applies at exact Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 plus Desktop #393, #396, #398 and #400. Four exact headless source replays passed. Native GPUI was not run.

## Normal path

Desktop already holds the accepted immutable widget tree in `Rc<Node>`. Closing a badge popup cloned the whole tree into its existing one-slot `last_popup`. Ordinary reopening cloned that slot again to seed a new independent popup while the extension process replied. Model's package renders a picker on its existing model-list path via the SDK's Picker schema with owned labels and arbitrary choice values. These two copies are real even if the process has not returned a replacement tree. The smaller 8-option fixture and a 512-option stress fixture are synthetic, not a claim about deployed model-list sizes.

Keep the same immutable root in the existing last-popup slot. Accept either an owned incoming root or a shared cached handle in `DeclarativeView::show`, converting only after the sequence check. A new accepted reply still has a separate root. Keys still clone; each newly opened view still has its own action sequence, fields, images, and rendering/focus preparation. No new cache, process round trip, or validation change. No prior sealed Desktop patch modifies these files, and #393/#396 (history), #398 (config snapshots), and #400 (SSE) do not remove these popup copies.

Only the copies at close and warm-seed are removed. An `Rc` may retain the original spare capacity that a length-sized clone would not; no peak-memory, allocation-global, or latency claim. Existing context-only `ClosePopup` messages are not view-generation-tagged; this patch makes no change to their scope. An inert old view may still receive its own late reply while retained; the held seed and separately attached new view are not mutated by it.

## Executed focused proof

The harness compiled the full exact `Node` and choice schema, protocol `parse`, and the production Runtime View handler arm. It compiled the actual badge `close_popup`/`toggle_popup` bodies, core Popup logical lifecycle, view show/snapshot/revision/action methods, unchanged keyboard action lookup and unchanged render root read. Native entity/window/image/process facilities are synchronous test carriers. SVG and icon lookups are intentionally unexercised stubs. The verifier also compares the exact unchanged rendering, image, field, and callback source contexts across arms. These checks are not native focus, pixel, image, process, detach timing, or keyboard integration tests.

Controls: cold and repeated warm before fresh reply, empty snapshot fallback, untyped view downcast, independent badge, different attached view IDs, a late reply to an old retained view then a detached old ID, mismatched session, stale action sequence/revision, fresh replacement and transition, unchanged key buffer independence and typed action value, invalid picker duplicates and field, and Weak root release when existing cache/view holders have gone. The view-session lookup and GPUI focus/image outcomes remain modeled; the associated production comparisons and calls are executed. The run observed per-view prepare invocations, not actual SVG/images. The changed source did not alter resizing or notify hooks.

| Fixture | Cycles without a new accepted reply for the reopened view | Whole-tree copies | Distinct new choice-label buffers | Distinct new choice-value string buffers |
|---|---:|---:|---:|---:|
| Picker with 8 options | 3 | 6 → 0 | 48 → 0 | 48 → 0 |
| Picker with 512 options | 3 | 6 → 0 | 3,072 → 0 | 3,072 → 0 |
| Picker with nested JSON choice values | 1 | 2 → 0 | 16 → 0 | 16 → 0 |

Counts are pointer identities on the exact two close and seed boundaries with both holders live. The nested case counts one string inside each choice value, not every nested allocation. Keys' unchanged clones, rendering, parsing, and temporary fixture snapshots are excluded. Full count/behavior assertions are in `carrier.rs`; equal behavior trace SHA is `ecba06d1fd652eb583dbdc2ec4be7391bad83324c38ff3b317c9667de1340e1d`. Source, fixture, dependencies, fresh Cargo JSON non-test binary and per-arm executable SHA before/after invocation are bound in `cargo-provenance.json`. No native, global allocator, timing, RSS, or remote work.

## Reproduce

Uses exact pinned sources, a sealed composed source, a warmed offline Cargo cache/target with at least 512 MiB workspace and temporary headroom, the exclusive common compiler lock, and a +200 MiB net growth fence. Set `CARGO_HOME`, `CARGO_TARGET_DIR`, `R77_BUILD_LOCK`, and `R77_RAW_CARGO_DIR` to absolute paths; create the raw directory. The original run used Rust/Cargo 1.95.0 and one job.

    bash verify.sh --prepare PINNED_DESKTOP_GIT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393 CUMULATIVE_PATCH_396 PATCH_398 PATCH_400
    bash verify.sh --run PINNED_DESKTOP_GIT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393 CUMULATIVE_PATCH_396 PATCH_398 PATCH_400
