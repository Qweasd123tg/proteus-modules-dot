# Core cancellation: nominal grace, not hard preemption

This is a mandatory source-only clarification for the Round 6 cancellation comparison, preserved with the historical synthesis. It adds no runtime result.

The selected Core consumer uses a **nominal asynchronous 500 ms cancellation grace period**. Tokio timeout depends on cooperative polling: it does not preempt a blocking `Future::poll`, roll back an external effect that already occurred, or itself stop all OS descendants. After the grace expires, the consumer stops awaiting the invocation and forms a canceled/timed-out result; that result is not a rollback receipt or a universal wall-clock stop guarantee.

Source: [Core invocation timeout/select/settlement at the researched pin](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/invocation.rs#L79-L122).

The corresponding selected Mastra `settleRunning` consumer waits for `allSettled` without its own local timer. Other tool-level deadlines were not investigated. This is not a demonstrated hang or an upstream runtime defect.

Read together with [publication context](../INDEX.md), [CAS test-layer classification](FOLLOWUP-CAS-WIRE-LAYER.md), and [LiveKit reply-status limitation](FOLLOWUP-REPLY-STATUS.md).
