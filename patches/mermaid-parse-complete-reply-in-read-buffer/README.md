# Mermaid Rust bridge: decode a complete buffered reply without copying it

When the first reader buffer already contains the terminating LF, decode the inclusive reply slice directly. Consume the accepted bytes before returning either the value or the decode error. Fragmented replies still assemble in the existing temporary buffer. The cap, framing, request loop, timeout handling, and SVG validation are unchanged.

On the pinned Rust 1.95 Linux host, the synthetic 2,139-byte reply used the existing BufReader buffer address on the new path. The old path copied it into a separate vector. Whether an actual pipe has the whole reply buffered depends on how it is read.

Verified on exact Extensions stock **923077d3** and on the exact predecessor with #412 applied first. Nine paired std-only tests passed in debug and optimized builds for both routes. They run the exact bounded reader and request loop against real std buffers and inert error/codec/channel fixtures, not the native package, Serde, or a live worker. No timing or process-memory claims.
