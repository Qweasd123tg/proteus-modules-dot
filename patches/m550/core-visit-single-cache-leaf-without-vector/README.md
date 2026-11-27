# Avoid a temporary vector for one ordinary cache leaf

An ordinary leaf is already one verified JSON value. Pass it through the
same page loop without a heap vector. Packed leaves keep their existing
vector, order, validation and decoding.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. The release cache-range probe observed one fewer
allocation request (72 bytes on this stand) for each overlapping
ordinary leaf. Two ordinary leaves saved two requests; packed-only,
empty and out-of-range controls were unchanged. Missing and bad-hash
ordinary leaves returned the same miss with one fewer request. All cases retained the
same output and candidate read-key order with no cache writes.

Both arms passed 24 selected view tests, including checked latest
and pinned cache reads. End-to-end latency and resident memory were
not measured.
