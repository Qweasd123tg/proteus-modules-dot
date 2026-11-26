# Reuse the encoded Anthropic body for transport retries

Prepare a single JSON request for completion or SSE. The adapter no
longer needs the original request or the rendered JSON tree during send
and backoff. A reqwest builder clone shares the encoded bytes. Existing
transport classification, the two retries with 150/300 ms delays, and
the first HTTP response (including 5xx) remain unchanged.

Apply to Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`. No alternate is needed.

Both unmasked optimized libraries built; 13 focused
native tests passed in each exact arm. Twelve loopback cases verified
exact body and relevant headers for both response modes and auth styles,
including 0/1/2 retries, exhaustion and HTTP 500/529 non-retry. Separate tests check
invalid headers send no request and dropping the caller future leaves no retry.
Three attempts built the encoded body 3 times before and 1 after. A valid
first attempt still encodes once and pays a template clone, measured in
isolation as 11 allocation/reallocation requests and 690 aggregate
requested bytes with shared payload backing at both tested sizes. This
does not measure app memory or latency. No real provider was used.
