# Count Git badge records without owning detail entries

The badge needs only a count and branch metadata. Use the same
porcelain parser and validation in count-only mode without creating
owned paths, rename origins or index-stage strings. Detailed changes
still collect the original rich records. Git invocation, bounds and
error order stay unchanged.

Apply to current Core `fc0297620c2b6d6d8ade8f524df6a4b99d6fae8b`. Strict apply and reverse passed.
The exact Git workspace module built in isolated native harnesses;
three tests per arm matched 14 output lines from real owned Git
fixtures and synthetic boundary cases, including details and index
strings. No whole Core/HTTP or extension run.

On 512 synthetic tracked records the parser alone issued
2056 → 0 Rust allocator requests.
This input has no branch header. The branch-only control stayed the same.
No process-memory or latency claim.
