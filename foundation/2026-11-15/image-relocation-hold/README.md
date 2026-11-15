# Image relocation: identity and resolver contract HOLD

This is a docs-only follow-up to the known resume-integrity P2, not a new finding or implemented fix.

- [Disposition and evidence boundaries](HOLD.md)
- [Independent contract review](INDEPENDENT-REVIEW.md)
- [22 source blobs: pinned links and verified hashes](SOURCE-VERIFICATION.json)

The durable ImageRef absolute path participates in canonical PartId identity. Rewriting it under existing IDs risks rejecting history or recorded model requests. A session-bound late resolver is a plausible solution, but its ownership, consumer coverage and recorded-versus-executed contract remain unresolved. Do not fabricate new IDs or weaken equality as a small workaround.

Related delivery PRs [#34](https://github.com/Qweasd123tg/proteus-modules-dot/pull/34), [#113](https://github.com/Qweasd123tg/proteus-modules-dot/pull/113), and [#131](https://github.com/Qweasd123tg/proteus-modules-dot/pull/131) do not close this issue.

Publication checks recomputed all 22 source Git blob SHA-1 and SHA-256 hashes. Source snapshots and raw logs are not included. No Rust compile, project tests, runtime/provider execution, relocation reproduction, or performance benchmark was run. No runtime improvement is claimed.
