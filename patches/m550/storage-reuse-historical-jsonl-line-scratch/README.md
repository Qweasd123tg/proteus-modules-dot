# Reuse raw JSONL line scratch during historical conversation reads

Allow an explicit historical conversation read to reuse one local line
buffer. Current, SQLite, selection of the previous revision or
pre-replacement state, resets, errors and full suffix validation are
unchanged. The backend already drops scratch allocations above 128 KiB.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. With 12 inline JSONL rows of about
72 KiB, the optimized typed Revision 0 and Revision 6 calls both
made 3 reallocations instead of 15 and requested 134,144 bytes in
reallocations instead of 1,231,862. These are cumulative requested
sizes, not live heap or peak memory. Realloc counters were unchanged
for tiny JSONL rows, Current and SQLite. Both native arms replayed all
12 rows and rejected a same-size valid edit after the selected cut.
117 tests passed and one was ignored in each arm.

Use source.patch for the exact base. For the exact recorded tree after
the rebased #853, use only the after variant from receipt.json. Other
pairs are source-only compatibility checks. No combined build, app
startup or PSS claim.
