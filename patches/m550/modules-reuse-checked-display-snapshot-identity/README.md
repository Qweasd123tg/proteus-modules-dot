# Modules: reuse a verified display-page request identity

A display-page request still has to match the full stored snapshot identity. After the existing source checks succeed, the response can use that matching owned request identity instead of cloning the three stored strings. If any request string has spare capacity, the response still clones the stored identity. Canonical record reads, paging limits, cursor behavior, source verification, wire and storage formats are unchanged.

108 tests passed in an isolated Rust 1.95 build of the pinned Modules owner with #803 and this patch; one existing manual benchmark stayed ignored. A typed test on JSONL and SQLite confirms ownership transfer and the spare-capacity fallback. Negotiated native workers compared the #803 predecessor with #803 plus this patch. A synthetic five-record fixture on each backend produced 13 matching ordered result or error payloads after normalizing only new handles and fixture locators.

The patch applies directly to the exact Modules owner and is independent of #803; both orders were checked. No claim of a separate native build without #803, production eligibility rate, Desktop timing, PSS or end-to-end speedup.

Use `source.patch` only on the four exact preimages in `receipt.json`. There is no alternate.
