# Usage history: search lowercase ASCII fields without copying

Match each whitespace-separated term directly against the four borrowed fields
when they are already lowercase ASCII. The original spaces between fields
cannot be part of a term. Uppercase and Unicode still use the original
join-and-lowercase path. Search hits, order, errors and output are unchanged.

The guarded native test compared 90 complete serialized results across 15
fixtures, with 60 allocation ledgers. A 512-request test avoided 1,024
allocation requests and 95,488 gross requested bytes. A 2,048-request cost-sort
test avoided 4,096 requests and 381,952 gross requested bytes. Allocation
peak was unchanged on those matching cases; retained requested bytes were
unchanged in every case. A 2,048-request no-hit test reduced the scoped
requested peak from 203 to 13 bytes. These are representative constructed
inputs to the exact filter, not an HTTP, application, wall-time or PSS test.

One production leaf. The exact patch applies and reverses on both owner
Extensions main and the actual Desktop extension pin, with no prerequisites.
