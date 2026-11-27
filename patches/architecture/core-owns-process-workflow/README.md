# Keep the process Workflow bridge with its Core runtime

This standalone patch targets Proteus Core `024fb944a91382026bb2aa5c7b8da65c284d0305`. Check `sha256sum -c SHA256SUMS` in this directory before applying `source.patch` to a detached Core checkout. It also applies cleanly after patch #943.

Previously the process adapter directory depended on the Core Workflow runtime to dispatch callbacks and settle invocations. Put that bridge under `core/workflow_host`; it depends on the existing process export client, configuration and callback codecs. Only the three shared codec functions become crate-visible. No new trait, public API, process, Cargo dependency, or wire behavior.

The bridge's invocation body and callbacks are unchanged, including stream closure, checkpoint rejection, cancellation and failure history rules. The file move removes the last direct production reverse import from process adapters or tools into Core when stacked with #943. The storage fixture's test-only import intentionally remains. This is a source layering change, not a Cargo cycle fix or a performance claim.

See `receipt.json` for exact source trees and native test results. The stacked tree is verified for strict application and inverse, not native execution.
