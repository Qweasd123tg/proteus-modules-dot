# Known M4: Anthropic failure propagation candidate

Delivery-only documentation and two alternative patch artifacts. Merging this directory into the delivery repository does **not** apply either patch to Proteus production sources. No auto-merge or automatic composition of upstream patches is proposed.

## Choose exactly one variant

- On Modules `c035142558f0fca43e9772fc0e50ca293abf1531` without PR108: use [standalone patch](anthropic-failure-classification.patch).
- After applying [PR108 stream ownership proposal](../model-stream-ownership/stream-state-and-delta.patch): use [rebased patch](anthropic-failure-on-PR108.patch).
- Do not apply both variants. Original PR108 and standalone M4 patches conflict in either order. The second variant explicitly resolves that textual overlap; it is not a tested combined build.

## Scope

Known M4, not a new finding. HTTP400 + invalid_request_error + exact `prompt is too long` or prefix `prompt is too long:` becomes ContextWindowExceeded. HTTP529 + overloaded_error + string message becomes Retryable. Only HTTP200 SSE overload or clean premature EOF receives Retryable/StreamDisconnected. Non-200 SSE failures remain Other, including previously admitted 1xx/3xx and other 2xx responses. Unknown/malformed payloads remain Other.

No recovery engine is added. Existing consumers retain retry/compaction ownership. Direct Rust Model::complete / PR99 boundary is **not fixed**. Reading the whole error body for streaming400/529 is additional work without a new size budget or performance measurement.

## Evidence and limits

[Report](REPORT.md), [independent review](M4-INDEPENDENT-REVIEW.md), [patch checks](PATCH-VERIFICATION.json), [publication recheck](PUBLISH-VERIFICATION.json).

14 supplied source blobs rehashed to their recorded Git SHA; standalone and PR108-rebased patches independently applied with whitespace checking and byte-compared against reviewed source. Four regression test functions are written but **NOT RUN**. No Rust compiler/toolchain, build, lint, tests, fixture execution, live providers or runtime validation. No claim of production readiness, runtime fix verification, or latency/memory improvement.

The report/review describe the preparation snapshot. Source working copies named in them are not included: only documents, manifests and patches are published. Historical M4 results are linked in the report, not presented as tests of this patch.
