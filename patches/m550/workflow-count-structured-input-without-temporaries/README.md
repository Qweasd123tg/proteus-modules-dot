# Count structured estimator input without temporary strings

Seven JSON Value lengths use the existing compact counting serializer.
The history estimator also borrows the length of ordinary tool error
or output instead of copying it, sharing the request-side precedence.
Structured/status fallback, opaque native hints, role and phase handling,
rounding, categories, and effective estimates remain unchanged.

Base: Modules f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
Both exact trees passed 13 focused offline tests and optimized library
builds. In prebuilt fixtures the estimator requested 72→8 allocations
or reallocations for structured request categories, 49→0 for structured
history pressure, and 2→0 (262152→0 requested bytes) for history with
256 KiB raw tool output. These are cumulative allocator requests,
not live or peak memory or timing. Existing same-file #862/#870 require
exactly rebinding selectors; their combination was checked at source
level but not run.
