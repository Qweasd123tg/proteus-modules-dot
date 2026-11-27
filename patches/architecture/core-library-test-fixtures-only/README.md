# Run Core library tests without the production worker bundle

Standalone patch on Core `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify `sha256sum -c SHA256SUMS`, then run `git apply --check /absolute/path/to/source.patch` in a detached Core checkout.

Only an explicit, unmixed `-p proteus-core --lib` selection takes the narrow path. It prepares the existing reference and session-storage fixtures separately; supplying both paths avoids both builds and does not require a Modules checkout. An inherited package map is not reused for this target. Arguments after Cargo's `--` are passed through without influencing fixture selection.

The full and legacy integration preparation rules are retained. Nothing changes in Core runtime, module packaging, Cargo dependencies or public interfaces. This reduces requested fixture build targets, not the implementation crates that the reference fixture still links. See receipt.json for actual verification and exact trees.
