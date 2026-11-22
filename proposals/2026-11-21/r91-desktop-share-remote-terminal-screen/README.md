# Desktop: share the attached terminal's visible frame

One patch for Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded`, checked on stock and sealed M150 Desktop through #413.

The attached agent terminal's worker already kept an immutable visible screen. Every UI snapshot deep-cloned the cached frame under its mutex, including each row vector and styled run string. The worker now moves the completed frame into an Arc, and each reader clones only that handle. Producing a frame adds a small owner allocation; it does not change how the VT engine builds its contents. The reader still requests a palette, restores frame credit, and sends the original wake in the same order. The next display frame replaces the cached owner without mutating old readers.

The attached view hides the cursor only for the finished process at the render consumer, including the drain state, without altering the shared frame. The local terminal's existing cursor decision and the cell drawing calculations are unchanged. This does not remove allocating the next frame or the text copied into native elements, and does not change terminal transport, command routing, default engine, queues, or app-level cache policy.

## Focused evidence

The four locked headless runs used the actual threaded Alacritty Display actor with the pinned local terminal crate. The test suite included the inherited local Alacritty smoke unit, not a separate app launch. The patch was checked against 46 previous Desktop patch hashes and 160 locked package identities, retaining inherited #251 grouping. No Ghostty, native GPUI, real window, remote service, latency, CPU, RSS, or full-workspace claim.

* **Real actor and palette wake:** after consuming the startup redraw, one palette-A request and one input feed produced a styled wide-glyph frame. With credit consumed, one palette-B snapshot returned A and then, without any extra snapshot, feed, or wake from the probe, the redraw channel delivered the updated frame. Default foreground changed; explicit RGB, text, row layout and cursor values matched otherwise. Held A and B readers kept their original data after palette or input replacement, and the candidate's obsolete frame owners released after the last reader dropped.
* **Scoped allocation:** for 16 same-palette reads of one stable 96×28 frame with 48 styled runs, the current reader thread's measured snapshot handoff went from 1,040 allocation requests and 62,208 requested bytes to zero. This is only the repeated read boundary after frame production; it excludes worker and paint allocations. Pointer checks showed the candidate used the same row and run-string backing, not a separately allocated equal frame.
* **Modeled native seam:** the verifier executed exact projection and styling code with recorded element operations rather than a GPUI window. It matched live focused fill, live unfocused outline, transport-finished cursor suppression, unchanged row geometry/style when hidden, and local/cursorless behavior. It independently verified the cached screen still had its pre-render cursor.
* `cargo-provenance.json` binds fresh Cargo test artifacts to exact manifest/source paths, input hashes, and pre/post execution executable hashes. `behavior.trace` is the common probe trace and `unit-results.log` preserves timing-free outcomes.

## Reproduce

From here, run `sha256sum -c SHA256SUMS`. Use `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS` to apply/verify exact source without running. Use `--run` with the warm offline locked cache/target, shared compiler lock, and fresh private output directory (`CARGO_HOME`, `CARGO_TARGET_DIR`, `R91_BUILD_LOCK`, `R91_RAW_CARGO_DIR`). The verifier checks minimum disk reserves, bounds extra disk usage and runs one Cargo job. Both source tiers use the existing Alacritty-only wrapper; the checked-in source is not modified by the fixture overlay.
