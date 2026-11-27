# Skip unused usage projection for pinned model-context reads

When a model-context query has to replay a pinned journal rather than
use the exact resident writer, build the model context but not the
unrequested usage summary. The entire fixed journal and all existing
handle, revision and latest-turn checks still run. Usage queries and
resident/writer paths remain unchanged.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`; full-index forward and inverse checked,
two optimized libraries built. Each component arm passed
117 tests, one ignored. With 24 settled synthetic
model exchanges, JSONL requested 3593→3546 allocations/reallocations
and SQLite 780→725; both decoded all 98 pinned records with the
same context and separate usage results. Plain two-record controls had
identical allocator counts. No whole-product RAM or time measurement.
