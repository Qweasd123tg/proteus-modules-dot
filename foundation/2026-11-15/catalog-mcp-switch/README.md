# Catalog MCP: binding identity versus effective switch

Source-only candidate for the **known** PR85 `catalog-mcp-toggle` family, not a new finding or production fix.

The receipt comparator excludes only `enabled`; every other field remains part of equality. Replacement preserves existing effective on/off even over a changed manifest default. An absent binding with a stale receipt cannot force-enable a new default. ACK/rebase full equality is unchanged: overlapping late enable remains an explicit conflict.

- [Report](REPORT.md): exact scope, contract and tradeoffs.
- [Patch](catalog-mcp-switch.patch): three paths, +15 implementation lines; no speed/LOC reduction claimed.
- [Independent source review](SOURCE-REVIEW.md).
- [15 pinned sources](SOURCES.json) and [blob/SHA256 verification](READ-VERIFICATION.json). Desktop base: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- [Mechanical checks](SOURCE-CHECKS.json): strict apply and candidate-byte comparison; publisher repeated these checks.
- [PR134 composition source](PR134-COMPOSITION-SOURCE.json): both patch orders byte-identical, **text-only**, not runtime integration.

**Six proposed Rust tests NOT RUN.** Rust build, rustfmt, native UI/ACK, HTTP/profile persistence and MCP execution NOT RUN. No upstream production source changed. This merges review artifacts into the delivery repository only.

Related: [known family #85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85), [JSON-form proposal #134](https://github.com/Qweasd123tg/proteus-modules-dot/pull/134).
