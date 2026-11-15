# Independent source review: shared metadata transport

Reviewed patch SHA-256:
`8983c8b8ec0c6acdb65f5495dc0509f68ee63ad57ae7d1c3adb352128e95eac7`.

Verdict: no source-level blocker found in the inspected change. This is not
compilation or runtime approval. The proposed Rust test was not run.

Reviewed the before/after catalog and quota readers, transport implementation,
new transport fixture, existing catalog/quota tests, request fixture helpers,
CodexAuth access/refresh ownership and client-version configuration. Repeated
strict `git apply --check --whitespace=error-all` against the supplied baseline.

## Preserved boundaries

- The helper owns exactly the existing metadata request sequence: initial auth,
  GET, at most one refresh after the first 401, terminal status checking. It
  does not call the inference retry policy or add retry/backoff for 429/500.
- Both endpoint owners retain their own total 30-second timeout, including
  lock admission, cache TTL and serialization, DTO decoding/validation, and
  cache publication only after success. Unsupported adapters return before
  auth as before. The helper returns the undecoded response.
- Catalog client-version lookup moves into the builder and may run twice;
  the inspected source reads immutable configured JSON, so this does not
  change the selected version. Query and endpoint construction remain local.
- Operation labels preserve exact status/error text. Transport cause handling
  still removes URLs; quota still deliberately discards malformed-body error
  details while catalog retains its existing contextual error chain.
- Access no longer survives successful helper return, but its inspected fields
  are an owned token and headers, not the refresh lock or a lifetime guard.
  Cancellation-safe refresh transaction remains in CodexAuth unchanged.
- The now-private metadata error formatter has one remaining caller inside
  transport; no sibling use was found in the supplied model-pack sources.

## Test review and limits

The addition is one proposed test method with six subcases: two endpoints by
terminal second-401, first-429 and first-500. It checks final diagnostics,
query/path and refreshed headers, request count and no cache publication.
Existing successful refresh/cache/decoding tests are not replaced. This is
not six executed tests or new production coverage until Rust runs them.

The listener is bounded by the enclosing timeout and joined futures. Closing
it after the allowed replies makes an extra awaited request unable to return
the expected terminal status. The configured endpoints are loopback. However,
`no_proxy()` is applied to the provider client only: OAuthClient has a separate
HTTP client. Do not claim OS network isolation or environment-independent
absence of proxy routing for the refresh leg.

No Rust/Cargo/rustfmt, HTTP fixture, provider call, full project test or CI run
was performed in this review. In particular, compilation and async Send/type
requirements still require the actual affected package gate.
