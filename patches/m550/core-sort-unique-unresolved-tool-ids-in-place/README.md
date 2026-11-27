# Sort unique unresolved tool IDs without a heap scratch array

Projection keeps the same lexicographic UID list and result filtering.
The input map emits its unique keys, so stable ordering adds no value.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. In an isolated fixture with 50,000 source map
entries (some filtered), sorting in place removed one allocation of
1,006,968 bytes. Empty and small controls had no difference. The output
matched an independently stable-sorted list. Each build passed 27
Semantics tests. No tool, startup latency or RSS measurement.
