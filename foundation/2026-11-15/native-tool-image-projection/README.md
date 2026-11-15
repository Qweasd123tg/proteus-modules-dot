# Native tool images: A1 remediation candidate

Start with [REPORT](REPORT.md), [independent review](TOOL-IMAGE-INDEPENDENT-REVIEW.md) and [patch](native-tool-image-projection.patch). Source-only candidate for known [A1 / PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85).

+63 production lines; seven proposed tests NOT RUN. No compilation, runtime or provider acceptance claim; no new image limits. OpenCode OTM-1 / PR102 remains unresolved. Upstream production and dependency pins unchanged.

Text-only composition evidence covers PR108, PR110 and PR112. Combining 110 with 108 requires [the published 110-on-108 rebase](../anthropic-failure-propagation/anthropic-failure-on-PR108.patch), not the standalone PR110 patch. Ten orders have byte-identical paired results; this is not integration testing.

Source snapshot references in manifests describe verification inputs, not files included in this package. Patch SHA256: `25c06b57d1200568811ca9f98eb77979fadf8c08d020d5b09fe656f9aa552e33`.
