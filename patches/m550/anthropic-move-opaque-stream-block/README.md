# Move opaque Anthropic stream blocks into state

Validate the redacted block's data as before, then take the entire owned
provider object from the temporary parsed event. Preserve unknown fields,
string contents, event emission, and surrounding ordinary blocks. Invalid
redacted input still errors before replacing an existing block.

Exact Modules base: `6b290ebff828427ab66ef9c4ff3b24cef3627603`. Strict indexed apply/reverse
verified. Both optimized unmasked model-pack libraries built.
32 focused native tests passed on each arm.
On a synthetic 512 KiB redacted block start, allocation requests of at
least 512 KiB went from 2 to 1; aggregate bytes requested inside
the translator went from 1053531 to 527163. This is not total application
memory nor elapsed time.
