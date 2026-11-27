# Format a finished tool result only if its display card is still present

Keep the lookup order for current and retained background cards. Only
format the result once it has a display consumer. Approval status updates
and matched-card formatting, truncation and metadata remain unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. A synthetic unmatched structured result avoided
6 allocator requests and 370,171 bytes of aggregate allocation traffic.
No allocations were observed for that candidate event in the isolated
update. Matched results and direct-text controls stayed the same.
Both release arms passed 18 targeted turn-progress tests. No real
tools were invoked. For strict tooling on top of #911, use the replacement
index line in the receipt without changing the code hunks.
