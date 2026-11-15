# OTM-1: source-only typed tool-result media bridge candidate

## Status

**Known OTM-1/P2 follow-up, not a new finding and not a runtime-confirmed fix.** The source proposal removes the pre-sampling PNG projection blocker and preserves typed tool-result media at the reverse compaction callback boundary. Seven focused test cases are proposed; **all are NOT RUN**. No project imports, syntax checks, Node/Rust tests, provider calls, native applications, build or install ran in this pass.

Independent contract and exact source reviews found no blocking issue in the proposed supported boundary. Integration qualification remains open. The prior runtime-readiness check for PR102 failed ESM linking on missing `effect` before test bodies ran; that is historical environment evidence, not a freshly repeated failure or a behavior test. No dependencies were replaced by stubs or installed here.

Patch `otm1-media-bridge.patch` SHA256: `c8fc57f2c515c8c967b6a0370a489c77ae6a332504ea0225f1d4ec0fdd2fd31f`.

## Provenance and composition

Read-only start/end refs agree: Modules `c035142558f0fca43e9772fc0e50ca293abf1531`, Core main `bcbda4435534a296c707a1daa250813d692f68e1`, delivery `6674cae3a120a35d6d199aed272a2ef843bcfd82` after PR130. The source patch is against Modules, not applied to upstream production.

Modules actually pins Core `41bdfffa6e70228278b4abc758b7f81a12672f35`; its ToolContent contract was checked separately. It is not replaced with Core main or asserted to be a tested mixed-version runtime. Native OpenCode remains `@opencode/core@2.0.22`, source pin `527f0b931d1f9b3ebd34e106c51b31ce5db5b075`.

Twenty-two source blobs are Git-blob verified: eight relevant Modules implementation/test/package files, ten pinned upstream producer/schema/projection/compaction files, and four repository/contract-context files. Separate manifests preserve those identities. `git apply --check --whitespace=error` succeeded; the applied copy is byte-identical to reviewed `after/`. These are inert source checks, not runtime evidence.

PR113's OpenAI/Anthropic tool-image serialization proposal is a different downstream boundary and does not fix OTM-1 by itself. This candidate neither qualifies that composition nor proves all providers receive/render images. Python candidates PR126–130 have no implementation dependency here and were not rerun. Known OTM-1 scope remains successful PNG-tool continuation; additional error/text cases support the common representation rule, not new reported incidents.

## Root cause and smallest useful boundary

`nativeContext` is shared by ordinary workflow token estimation and native compaction. The existing file-tool adapter emits canonical Image content for the upstream PNG reader, but nativeContext rejects every non-text ToolContent. A successful read can therefore stop the workflow before its next sampling even with no compactor, as already documented by PR102.

Removing that guard alone is incomplete. Pinned upstream durable tool states use `Tool.Content` text/file blocks. `toLLMMessages` converts completed tools into a text or content result; failed tools become an error value containing `{error, content}`. Existing `canonicalPrompt` JSON-stringifies those content/error values, losing typed media in the Core compaction callback.

The candidate adds two private helpers to existing `compaction.mjs` rather than another package or projection framework:

1. **Forward:** output stays the first native text block; canonical text blocks stay ordered; inline `image/*` becomes native `{type:'file', mime, uri:'data:<mime>;base64,<data>'}`. The existing native producer normalization is not rewritten.
2. **Reverse:** native content arrays and recognized error envelopes are decoded into canonical output plus ordered ToolContent. Only a leading text block becomes output. If the first block is an image, output is empty and all content stays in order. Call identity, failed status and the known error message are retained.
3. **Fallback:** scalar/text/JSON results and non-envelope error values retain their prior conversion. Error values are not assumed universally to be structured envelopes.
4. **Explicit unsupported content:** binary/PDF, Json ToolContent and non-inline/mismatched native file representations are not silently turned into base64 text. The candidate adds inline images, not a universal attachment bridge.

Both estimation and compaction use the same forward rule; the reverse counterpart prevents the callback from undoing it. Typed content does not undergo an unused JSON.stringify before conversion. No canonical history rewrite, file access, URI fetch, permission/admission change or new provider capability is introduced.

Production file size is **233 → 269 lines (+36)**. Tests add 140 lines and docs 24. This is a semantic consistency improvement, not LOC reduction, allocation elimination, measured RSS/latency improvement or an alternate estimator.

## Intentional changes and limits

- Multi-text native results now return as output plus text blocks instead of a JSON-array string. Known error envelopes now retain output/content and extract error.message instead of stringifying the entire envelope. These are intentional prompt-representation changes, not byte-identical compaction requests.
- The guarantee sought is ordered canonical model-visible content and failed/error semantics, **not exact ToolResult DTO round-trip**. Original metadata/filenames are not recovered; upstream can remove empty text; an original failed `error:null` already falls back to output before native conversion. A later provider can render failed-result fields differently.
- Image MIME/data are carried without format conversion, resizing or a new image-size budget. MIME `image/*` representation support is not provider acceptance or base64/content validation. Added native data-URI representations also have a memory cost; no benchmark was taken.
- Pinned upstream deliberately flattens/prunes media in reduced compaction requests. That policy remains unchanged: images are not promised in every summary attempt. Native-provider remote compaction remains unsupported by this adapter.
- Error envelopes are estimated differently upstream from successful content arrays, potentially including JSON/base64 text. This proposal does not repair upstream error-image token estimation or promise complete accounting.
- User attachment handling, including non-inline user images, is untouched. Tool Binary/PDF/Json remain unsupported here. Native provider lowering and Core+Modules deployment compatibility remain unqualified.
- No previously excluded security/process-authority direction was investigated. Existing unrelated tests in the files are not part of any claimed execution.

## Proposed regression gate: NOT RUN

The proposed tests use real pinned upstream APIs when their official dependencies are available; fake host/model callbacks are the existing test style, not replacements for Native Step/Effect.

| Proposed cases | Intended boundary |
|---|---|
| 1 native-context case, success/error subcases | Ordered output/text/image and failed state; immutable input. With measured anchor disabled, successful image adds the pinned native 1500-token estimate relative to an otherwise identical text-only control. This assertion has not executed. |
| 1 actual native-compaction callback case, text/image/error subcases | Core callback retains typed output/content/error, including existing scalar text and multi-text representation change. |
| 1 image-first native-content case | Later text is not moved ahead of an image when leading empty output is absent. |
| 1 unsupported-content case | Forward Binary/PDF and Json remain explicit rejection. |
| 2 workflow cases | Successful PNG result reaches second sampling once, with compactor absent and with actual native compactor auto:false. |
| 1 native file-producer case | A private valid 1×1 PNG passes actual native read into compatible native context projection. |

**Seven proposed test cases, zero executed passes.** Error/string/null fallback and reverse unsupported-file branches do not have additional dedicated controls in this patch; source inspection, not executed tests, supports those branches. Broader MIME/provider behavior is not tested. The proposed tests must pass with the exact locked dependencies before integration confidence increases; a helper-only substitute would not qualify the full service path.

The PNG bytes were generated as a tiny synthetic fixture with stdlib PNG chunks/CRC, not read from user data. That fixture preparation is not project-runtime validation. Historical benchmark datasets, scores, graphs, grades and user sessions were not used or changed.

## Evidence and handoff

- `CONTRACT-REVIEW.md`: independent supported-shape/semantics analysis.
- `SOURCE-REVIEW.md`: independent exact candidate and proposed test review, including final patch revision.
- `MODULES-SOURCES.json`, `UPSTREAM-SOURCES.json`, `CONTEXT-SOURCES.json`, `READ-VERIFICATION.json`: source provenance.
- `SOURCE-CHECKS.json`, `DIFFSTAT.json`, `FRESH-REFS.json`, `END-REFS.json`: inert checks and ref boundary.

Upstream production and delivery were not changed by this worker. This is a source-reviewed candidate for the known bridge family. OTM-1 should remain marked **not runtime-qualified**, with the pinned dependency/integration gate explicitly open.
