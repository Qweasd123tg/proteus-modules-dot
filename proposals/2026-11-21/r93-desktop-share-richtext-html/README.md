# Desktop: reuse accepted RichText HTML in the update guard

One production patch for Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded`, checked on stock and sealed M150 Desktop through #415.

Normal plain and Markdown renderer responses carry an HTML string in each RichText node. The native adapter used to make a second full copy of that string only to avoid resubmitting identical HTML. It now shares the accepted string with its memo. The existing String deserializer retains the same required-field errors; the decoded buffer moves into a small immutable owner. At mount and on a changed value the adapter shares that owner and passes the same borrowed bytes to the same native constructor or setter.

The memo still compares exact byte values, not owner identity. Independently decoded equal roots can retain their own backing while the adapter keeps its older equal value. Inline slots still sync independently, including when only their specification changes; their existing configuration can require a separate parser update. This does not share the native TextViewState's latest-input, parser queue, or parsed-document storage, or change renderer wire, readiness, selection, validation, or fallback policy.

## Focused verification

Four fresh headless artifacts ran the real Desktop protocol/DTO and exact RichText preparation, memo, element and view readiness methods with modeled native state and inline effects. The asset-free fixtures reflect plain and GFM renderer wire shapes; they do not run the renderer or native parser. The source gate checked 47 prior patches, 125 locked dependency identities, stock and cumulative apply/reverse/format, and full unchanged vendor text state and element sources plus existing inline implementation bytes within each tier.

* Across 24 separate retained synthetic elements (12 each of 58,621-byte plain-link and 52,593-byte GFM-shaped HTML), duplicate adapter memo payload was **1,334,568 bytes before and zero after**. Pointer tests prove that the accepted body and memo share storage in the candidate; bytes supplied to the separately owned modeled native state stayed identical. A small owner allocation remains per decoded HTML, and the original String's capacity can outlive its original root if the memo still uses it. This census is not viewport, renderer, transport, or process memory.
* The actual typed parser preserved empty and Unicode HTML, exact errors for missing/null/invalid/duplicate/unknown fields, inline sizes/counts, and the existing localized content error versus panel validation error. One typed fixture path decodes off the receiving thread and transfers the resulting node.
* Distinct equal HTML kept the existing modeled entity and suppressed the text setter, while changed inline values still reached the exact sync call. Changed same-length bytes and empty HTML reach the same native API boundary. Modeled commit/readiness, source-revision and rehost/selection calls matched; a superseded shared body is released when the last holder drops.
* `cargo-provenance.json` binds fresh non-test Cargo artifacts to exact manifest/source paths, locked inputs, and executable hashes before and after invocation. The four traces match byte-for-byte.

No native GPUI, real renderer, parser/paint timing, RSS, or full-app result is claimed.

## Reproduce

Run `sha256sum -c SHA256SUMS` here, then `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS` for exact static checks. Use `--run` only with the existing warm offline locked cache/target, exclusive compiler lock, and a fresh private output directory (`CARGO_HOME`, `CARGO_TARGET_DIR`, `R93_BUILD_LOCK`, `R93_RAW_CARGO_DIR`). The verifier uses one Cargo job, checks disk reserves and bounds extra disk consumption.
