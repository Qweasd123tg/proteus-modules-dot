# Borrow already-owned fields while saving the durable catalog

Serialize the summary, source stamps and fingerprint by reference.
The on-disk schema, checksum, validation and temporary-file protocol
remain unchanged. The read side still owns the decoded catalog.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. A synthetic Linux release
durable-save test requested seven fewer allocations, 602 fresh bytes
for JSONL and 603 for SQLite, with the same sidecar bytes, exact
load result and reallocation counters. 117 native tests passed,
one ignored per arm. Both exact release libraries compiled.

Use source.patch on the exact base. A source-only rebase after #858
and exact commuting trees with #860 are recorded in the receipt.
No application timing or resident-memory claim.
