# Build the canonical Text part directly

Move the input string into its one final canonical part. Use the same
role defaults, part and message ID creation, ownership and field
initialization without a temporary vector of raw content parts.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. A release batch of 50,000 new
messages from preowned strings requested **100,000 → 50,000** allocator
calls and **14.8 → 8.0 MB** cumulatively. This is construction traffic,
not a measured peak or history-load result. All 163 Contracts tests
passed per arm, including all role defaults, buffer pointer/capacity and
wire parity after normalizing generated IDs. The same patch applies
after #903; the receipt records exact forward and inverse source trees.
