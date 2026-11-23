# Plaintext: reuse the escaped URL for its visible label

The plaintext renderer already escapes each accepted URL the same way in its href and visible label. Escape it once for the href and append the same escaped bytes for the label. The copy uses byte offsets into the output string, so it remains valid if appending grows that buffer. URL recognition, the four escapes, and all output bytes remain unchanged.

Exact Extensions stock **923077d3** and the same source with Markdown patches #519 and #541 apply and reverse cleanly. Eight Rust 1.95 focused tests pass in both debug and optimized mode for both variants. These pair the exact lifted render and escape functions with an inert source of link ranges and output sink. They do not run the Markdown parser, the wire serializer, or the application.

Each accepted URL now takes one escaping pass instead of two. The displayed label still has the same complete bytes. There is no timing or physical allocation claim.
