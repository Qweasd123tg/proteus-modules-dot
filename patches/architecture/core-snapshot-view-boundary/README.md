# Stop storage snapshots from importing the display view

Standalone Core patch on `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify `sha256sum -c SHA256SUMS` and apply `source.patch` to a detached Core checkout.

Snapshot and record scanning now use a shared prefix representation rather than importing it from the display view. The stable source identity is defined next to snapshots; the display cache still owns revision encoding. This removes five direct snapshot-to-view references, not all session-store coupling.

Identity comparisons still use session locator, full committed revision and content SHA-256, not transient snapshot handles. Cache bytes, hash inputs, limits, validation, fallback, call order and replaceable storage worker contracts are unchanged. No performance claim. Receipt includes source composition and actual tests.
