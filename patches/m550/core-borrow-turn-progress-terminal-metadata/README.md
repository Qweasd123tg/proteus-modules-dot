# Decode live turn tool-terminal metadata by reference

The display projection borrows the existing nested JSON when reading the
terminal hint, matching the durable transcript reader. Prior-binding
fallback and raw/compacted metadata are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. In the release fixture a normal terminal object
saved 6 allocator requests and 410 requested bytes during the update.
Both arms passed 18 selected tests. The mixed fixture checks objects,
positional input, malformed/unknown or absent metadata, and both compact
and raw output. No real tools or terminals were started.
