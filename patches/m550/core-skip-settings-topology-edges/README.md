# Skip graph construction for the settings builder

Settings use the topology's module/tool lists and warnings, not graph
edges. Skip only those edges on its private route. Public inspection
and CLI still build the full graph including ordered hook edges.

Exact Core `024fb944a91382026bb2aa5c7b8da65c284d0305`. 146 targeted release tests passed per arm.
Both public topology and settings response bytes match on every fixture.
At 8 inert tool rows, the settings topology build saves 129
allocation requests and 11,889 cumulative requested bytes.
At 256 it saves 1621 requests and 143,369 bytes.
The fixture does not launch modules or model providers. These counts are
not app startup, latency or process PSS. Strict apply and reversal pass
with the preceding compatible settings/replay stack.
