# Core: release owned workflow input before waiting for the broker

A process Workflow moves its owned structured input to the internal invocation helper. The helper serializes it once, then releases the typed copy before broker admission can wait. The encoded JSON and other owned history remain. The serialized payload and existing borrowed callers, pre-cancel and error precedence, callback/stream handling and public wire format are unchanged.

18 tests passed on the exact standalone candidate: 10 cancellation tests (including two new ownership/error tests), 2 broker tests and 6 separate AgentAppServer lifecycle tests with an inert external workflow and no live model. The new ownership test checks that the typed input is released while admission is still blocked and that the entire payload echoes in the worker's existing response envelope. The earlier test assertion was corrected to compare that payload, not the envelope; product bytes are unchanged from that earlier source.

These direct Rust 1.95 tests used the existing locked dependency artifacts. The 16 common behavioral control tests also passed on the independent #806 build; that is not a byte-identical stock A/B. No latency, PSS or end-to-end speedup was measured.

Use `source.patch` on the exact Core owner and three preimages from `receipt.json`. There is no alternate. #806 is optional and source-compatible in either order; the combination was not built. Do not also apply the earlier unshipped source versions.
