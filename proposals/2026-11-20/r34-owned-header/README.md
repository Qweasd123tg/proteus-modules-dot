# Core: consume the previous owned display header

Base: Proteus-harness/Proteus-core `048378da7cbe890d8bf8a0152e55eb28ecb5013d`. Use `git apply --check` before applying the included source diff. This proposal does not change Core upstream.

Incremental publication already owns the decoded previous display header. Move it into the one-shot publication attempt rather than cloning sections and tools before replacing them. Keep the previous source and row count for the transcript base. Full fallback reloads independently. The source comparison, validation, prefix scope, sequence of cache operations and failure behavior are unchanged.

The isolated release Rust harness includes the exact actual incremental function and cache storage logic with a controlled storage/validation fixture. Return values, all cached values and ordered request traces matched byte for byte in nine cases, including three late fallback cases. One appended row on 5,000 prior visible rows saved 229 allocation requests and 23,007 cumulative requested bytes; on 20,000 rows it saved 866 requests and 89,255 bytes. Prefix and length rejection allocations matched exactly. Not a peak RSS or end-to-end runtime claim.

The two independent allocation changes were also applied together for Core remote-view regression tests: 16 passed (including missing and stale cache, append, packed and over-budget pages). The isolated A/B attributes only the named change.
