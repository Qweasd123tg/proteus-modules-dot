# Skip a chat row-key set when nothing can be pruned

A transcript splice previously built a set of every displayed row key, even when all five stores that use it were empty. This is their initial state when an existing chat first displays a populated history. Build the set only if replies, tool diffs, expanded rows, full blocks, or opened chains can need it. If any one is populated, run the same five retention calls in the same order.

The displayed transcript selection, splice and non-splice handling, and image retention are unchanged. Image retention still runs on every splice and still prunes the shared thumbnail cache, including with no local images. No payload, transport, retention rule, or cache limit changes.

In the isolated 50-row first-splice fixture, the change removed 50 key visits and one 592-byte allocation request. With only the image store populated, the same key set disappeared; all three image-ID visits and the image set's 84-byte allocation request remained. All populated-cache controls retained the original path.

The exact synchronous source was lifted into a standalone Rust 1.95 test harness with inert row, scroller, worker-owner, and shared-cache adapters. Seven paired tests and a 256-case state matrix passed in both debug and optimized builds. Both source files applied and reverted to exact bytes and modes. This is allocation work in the fixture, not native startup timing, RSS, GPU use, image decoding, or running the complete desktop app.
