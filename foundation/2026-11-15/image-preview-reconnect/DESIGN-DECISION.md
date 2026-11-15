# Reconnect rearm policy

Isolated source-only prototype for known PR85 round8-desktop image-preview failure caching. No tests, HTTP, real attachment, native window or project executable has been run.

The existing Connected handler already distinguishes recovery by checking link_error before Session::stream_connected clears it. This proposal reuses that boundary, without timers or transport/decode error classification.

At that boundary:

- Existing Failed slots become Waiting, eligible when their row is next demanded.
- Existing Loading slots get one boolean rearm_on_failure. This includes admitted-but-queued work, even if its HTTP starts after the boundary: it is explicitly a scheduled-before-reconnect policy.
- Ready and Waiting slots are unchanged.

A matching completion consumes the boolean. Success becomes Ready as before. Error with the credit becomes Waiting instead of Failed; an ordinary error remains Failed. The completion's key/ticket/Loading check still occurs first. Every fresh fetch_images slot starts with false, so an error in the replacement attempt is cached again unless another actual reconnect granted a new credit.

Several reconnects before the same completion coalesce into one credit. Duplicate Connected without link_error grants nothing. A sequence of distinct reconnects can grant further attempts; there is no fixed lifetime retry count or global request-rate bound. Existing global concurrency and pending queue limits are unchanged.

Rearming is not an immediate request. It relies on later demanded rendering, through unchanged missing/fetch_images/admission. The production pump notifies after Connected and the renderer calls missing, but actual native scene/list wakeup is not demonstrated here.

This covers both error-before-reconnect and old-attempt-error-after-reconnect at the state level. It does not repair image-only errors while SSE remains healthy, supply manual retry, classify transient versus permanent failures, or guarantee a successful retry. Permanent decode errors also get a chance on a later reconnect. No backend replacement/rebind policy is changed.

One private Slot completion helper centralizes consumption of the rearm credit and result-state assignment. This is a small state invariant, not a new task/retry framework or a performance optimization.
