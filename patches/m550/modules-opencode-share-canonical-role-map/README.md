# OpenCode JS: share the canonical-role lookup

Reuse a private lookup table when projecting a canonical history into an OpenCode JS request. The role conversion, validation and request shape stay the same, but the source no longer creates a new lookup literal for every message.

This is the JavaScript adapter's request path, not the Rust OpenCode Go runtime or Desktop startup. The receipt describes isolated request verification and an operation count, not application timings or V8 heap measurements.
