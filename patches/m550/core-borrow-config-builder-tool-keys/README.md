# Borrow the temporary tool inventory keys

The configuration builder owns the returned tool names but only borrows
their names for the temporary sorted lookup. Keep the same order, duplicate
precedence, owner checks, warning order and enablement flags.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 58 targeted release tests passed per arm.
The native probe compares complete ordered tool/warning JSON, including
overlapping process owners and distinct Unicode spellings. The empty case
is unchanged. The 69-tool and 517-tool synthetic inventories avoid
70 and 518 allocation requests respectively.
The allocator byte totals include transient container effects, not just
name strings, and do not measure PSS or startup. Strict apply and reversal
pass alongside the preceding configuration and replay stack.
