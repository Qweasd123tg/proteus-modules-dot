# Desktop saved-history page: exact late growth for the raw JSON

A single M387 Desktop selector in `src/api/mod.rs`. Core's `/history/page`
response is a sized JSON body, and a 50-row page can contain large tool results.
Desktop holds the raw UTF-8 JSON while its typed page is decoded. The current
raw buffer can round up from about 4.77 MB to 8 MiB. With a fixed large length,
reserve the final capacity only after actually receiving enough bytes to have
exhausted the previous capacity. Reserve one byte more than the announced
length for the final read-to-EOF check. Keep reading to EOF using ureq; don't
truncate the record to the optimization hint or change UTF-8/JSON validation.

Only successful fixed-length `application/json` history pages with a useful
allocation saving qualify. Small pages, unknown-length or decoded-size
responses, non-JSON bodies, non-success statuses, other routes and lengths
outside the optimization range use the old reader. 16 MiB is an optimization
bound, **not a new page limit**; the verified 17,303,667-byte page still loads
on both arms. The reservation does not trust a header on its own. The two
bytes at the growth boundary are carried into the same full UTF-8 check;
a multibyte scalar may straddle both reads. The stock reader still handles
errors ahead of UTF-8 rejection, and the patch preserves that precedence.
No request paths, query parameters, bearer headers, options, HTTP status
classification, deadlines, row boundaries or display model change.

## Native replay

Rust 1.95; exact pinned ureq 3.4.2 and ureq-proto, Desktop GET and blocking
idle transport, typed Core (50-row) page and JSON schema. Core's exact
`Full` response and desktop saved/older entry points are authenticated; the
harness substitutes a real loopback HTTP responder at the wire boundary.
The executable does not run a product Core server or GPUI. It fixes the
synthetic loopback proxy choice to no proxy, and omits ureq's optional
convenience JSON helpers because these GETs use the same body code and
separately pinned serde_json. This is not a TLS/release-binary test.

Four tests, 19 responses each per side in default and preserve-order JSON
layouts. The expected typed pages are compared in full. HTTP status bodies,
truncation before/after the hint, an oversized forged header, invalid UTF-8
(including in ignored fields), truncation with invalid UTF-8, trailing JSON
junk, chunked and close-delimited bodies, MIME/route/status fallbacks,
small/exact-power/above-range lengths, and a split multibyte scalar all pass.

| 50-row projection on synthetic 50,000-row history | JSON bytes | Old raw capacity | New raw capacity | Capacity removed |
| --- | ---: | ---: | ---: | ---: |
| First visible saved tail | 4,773,603 | 8,388,608 | 4,773,604 | 3,615,004 B |
| Earlier requested page | 4,787,113 | 8,388,608 | 4,787,114 | 3,601,494 B |

These are native raw-buffer capacities at JSON decode, not process RSS/PSS,
app latency, or a diagnosis of an external report. TCP chunking changes
small ancillary allocations; their sample counters are diagnostic only.
The raw capacities and observable typed results/errors replay exactly.

`composition.json` pins the selectors through #628, including overlapping
SSE selector #613. Apply and inverse restore exact bytes, and applying this
selector before or after the prior suffix yields the same production leaves.
Run `sha256sum -c SHA256SUMS`, then `python3 verify.py --vendor PATH` with
the pinned Rust/registry closure and local TCP loopback access.
