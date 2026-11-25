# Extensions: skip Markdown parsing for plain text without a lowercase web URL

The plain-text renderer no longer parses a full Markdown tree just because text contains a non-web URI such as a file or SSH URI. The existing parser still receives the complete input whenever a literal lowercase HTTP or HTTPS prefix could produce a link. Markdown rendering and the link parser rules are unchanged.

A detached Rust comparison used the actual plain-text render path, its pinned Markdown parser and the ordered wire helpers. All 18 fixtures (72 runs) produced byte-identical ordered output. With a synthetic 64 KiB dump containing non-web URIs, parser calls fell from one to zero and allocation requests from 8,415 to 20. Peak requested bytes in the renderer fell from 2,542,082 to 169,394; retained requested bytes were unchanged. This does not measure latency, real-application RAM or the frequency of this workload.

Applies directly to current Extensions and the Desktop-packaged revision; no predecessor patch is required.
