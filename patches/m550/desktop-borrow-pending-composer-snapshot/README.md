# Desktop: borrow the pending snapshot for the active composer card

Selecting one approval or question no longer copies every outstanding request or
queued draft. Question rendering borrows the immutable snapshot and can still update
its separate answer drafts. Request lookup, first-match order, approval callbacks,
paging and outgoing responses keep their existing behavior. No cache or new ownership
state. The two-leaf patch applies to the verified M438 Desktop source.

The bounded native fixture tested the exact card selector across 18 cases and 72
allocation ledgers. For a small selected approval alongside four unrelated ~2 MiB
payloads, requested peak in the selector dropped from 8,393,828 B to zero; neither
route retained heap after selection. This is a synthetic allocation test, not a
full GPUI render, approval action, latency or process-memory benchmark. DTO clone
fields were lifted from the pinned Desktop contracts dependency, using real
serde_json values and a synthetic presentation boundary. See the receipt for inputs
and identities.
