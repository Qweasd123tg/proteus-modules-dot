# Bound structured tool-result formatting to the live preview

Live progress writes at most the existing 10,000 preview bytes, rather
than joining a full result first. It keeps the same UTF-8 prefix and
separator rules. The existing unbounded display API still returns the
full text and uses the same borrowed text pieces and exact join.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. A matched fixture with a large leading JSON item
used 832,383 → 42,805 requested allocator bytes. Direct-text counters
were unchanged. Full and bounded text matched the original byte oracle
on every fixture, including escaped JSON and Unicode splits. The near-limit
two-text-item case did incur more cumulative allocation traffic
(20,108 → 42,708 bytes). The writer bounds the generated preview,
not geometric allocation growth; details are in the receipt.

Both release arms passed 18 progress and 161 Contracts unit tests.
The receipt records how to rebind the exact source after #911 or #912.
No end-to-end latency, process memory or actual tool run was measured.
