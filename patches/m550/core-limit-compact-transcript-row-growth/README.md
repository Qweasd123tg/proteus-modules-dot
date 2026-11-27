# Reuse the bounded tail growth rule for compact transcript rows

The two certified compact-text render paths now use the existing lazy
growth rule from the full-row path. Only when an accepted row needs more
space, try reserving the bounded remainder instead of doubling. Rendering,
filtering, ownership and serialization are otherwise unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. On both staged-text and typed fallback, the
50,000-visible-row fixtures ended with 50,000 rather than 65,536 slots.
At 48 bytes per slot this is 745,728 fewer bytes in the output row
array (not an application RSS measurement). Zero/32,768 visible rows and
the 4,096/65,536 input boundaries retained ordinary capacity. Serialized
output exactly matched the full-render oracle in each fixture.

Both release builds passed 62 targeted transcript and staged snapshot
tests. This does not measure full startup latency or total memory.
