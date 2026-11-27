# Move the existing locator into WriteCache snapshot preparation

Reuse the input SessionLocator instead of cloning its owned key; keep
the original SessionId for the same fresh identity check after fsync
and before rename. All source/prefix tests, disk activity and cache
publication or rollback stay in the same order.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. The optimized typed probe found one
fewer fresh Rust request for 353 bytes (the locator key length) per
existing-cache replacement, stale-prefix decline and forced rename
failure, on both backends. No fresh request count change before
snapshot preparation on the unmaterialized reservation control.
Both native suites passed 117 tests with one ignored, including genuine
stale-after-append, foreign source rejection and old-cache preservation.

Use source.patch for the exact base, or the exact after-#892 selector
in receipt.json. No combined native test, app latency or PSS claim.
