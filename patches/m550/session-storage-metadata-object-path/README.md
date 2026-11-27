# Build metadata object paths in one reserved buffer

Use the same private path helper for existing object hydration and new
object storage. Keep the parent path's native bytes, exact digest
spelling, integrity checks, collision verification and on-disk format.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. Optimized Linux storage-library
A/B on both JSONL and SQLite, using a real synthetic CAS-created
object, removed two fresh allocation requests and three reallocations
from each successful metadata read and idempotent CAS replay.
Missing-key totals, typed responses and persisted object/ledger bytes
matched. Both native suites passed 118 tests with one ignored,
including exact native path bytes and hash spelling/error order.
No app latency, PSS, or Windows runtime result is implied.

Apply source.patch on the exact base. Receipt includes exact
source-only alternates for #867 and the M650 selected composition.
