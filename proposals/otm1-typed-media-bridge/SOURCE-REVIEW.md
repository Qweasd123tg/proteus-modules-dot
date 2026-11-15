# Independent exact source review: OTM-1 bridge

Verdict: source-acceptable bounded candidate, with runtime/integration gate still open. No blocking source defect found. No Node/Rust/compiler tests, project import, native file operation or workflow was executed by this reviewer. The seven additions are proposed tests, not passes.

Independently hashed final patch `228edc2ada9b8f481cc2cab118e3cf752ffbef0f4c74c35feffd462e858788d1`. Modules baseline c035142558f0fca43e9772fc0e50ca293abf1531 and upstream pin 527f0b931d1f9b3ebd34e106c51b31ce5db5b075 remain coordinator catalog provenance. Reviewed the exact diff, relevant existing test fixtures and pinned schema/projection/estimation sources.

## Production contract

Two private helpers replace the forward rejection and reverse unconditional JSON stringification at their existing common boundaries. No new export, producer change or alternate workflow estimator is introduced. Forward retains output first (including empty string), preserves ordered text/image content and emits image/* data URI file blocks. Binary/Json/other unsupported canonical content still rejects. Reverse consumes pinned content arrays or known error envelopes, moves only a leading text block to output, and leaves image-first order intact. MIME and payload are preserved for matching inline data URI/file MIME; non-inline or non-image attachments reject rather than falling back to base64 JSON text.

The pinned durable tool serializer produces single completed text as type:text, multiple blocks as type:content, and failed state as type:error value {error,content}. Those paths match the helper. Non-envelope scalar/JSON fallback is byte-for-byte the prior expression, including its existing JSON-string error behavior. Recognized-envelope error.message is retained; string/other error fallback is explicit. Original error:null is already converted to output by forward state construction and is not promised to round-trip as null. Call id/status and content order are preserved at this boundary, not original metadata or every upstream representation detail.

Typed multi-text reverse is an intentional prompt representation change, not byte-identical behavior. Documentation says so. Existing upstream empty-text normalization and flatten/prune policy remain unchanged. This is not a guarantee that every provider renders all failed-result output/content: downstream error precedence still applies. Unknown malformed DTO validation is not a new contract here.

## Test plausibility and limits

Read the four compaction additions, two generated workflow tests and one files test. Imports/private helper use are coherent: tests exercise existing exported nativeContext/runNativeCompaction/createCompactionExport rather than exposing helpers. The compaction fixture inserts the matched call/result into the older exchange before the last retained user anchor; its 200000-token window and tiny payload are consistent with testing the unflattened callback branch. Deep equality is appropriate for these fixture DTOs with explicit error strings/null and null metadata, not a universal round-trip promise.

The image-first test removes the leading empty native text intentionally and checks output empty plus image/text order. Workflow controls check exactly two model starts, one tool execution and the original canonical image result at the second start, both without a hook and with auto:false. The file test goes through the real native read producer and then nativeContext; it has not run. Existing native dependencies and native service behavior are not simulated away, and missing dependencies remain an execution blocker until independently resolved.

Coverage limits: new tests do not separately exercise scalar/JSON error fallback, original error:null on failed results, non-PNG image MIME, or reverse rejection of malformed/non-inline native files. Those paths were source-reviewed; no claim of executed coverage. The forward finite-estimate assertion uses the existing measured-token fixture anchor, so it does not independently validate image estimation math. Upstream content estimates media categorically, whereas error envelopes can still stringify base64 for estimation; no equivalence/accuracy claim should be inferred.

## Candidate hashes

- compaction.mjs: `7711057e0d74c8213b44518c0697b433c5bd8289a8ee21c2aadfe29619dd9c61`
- README.md: `dfe5ab08ba476201e9b4f8e0d6a7d8f0c9028dc70007158afca04a4d5a4e7632`
- tests/compaction.test.mjs: `b6fe1aa7b9750c7e6d8f49e94702a8a4aceea462e36095bb9d604de29444087d`
- tests/workflow.test.mjs: `97e9980624c21124e34bb95af9a535848cc014e86b5743e1ec71b1764921a197`
- tests/files.test.mjs: `471cd48b0bfa590a2175e5a551dc1262e29e504387a317882ecf916340828c94`

This is a meaningful source-level fix for the known normal image-result projection failure, not full upstream/Core execution proof, provider format acceptance, complete media support or measured performance improvement.

## Final test-only revision

Independently read and hashed patch `c8fc57f2c515c8c967b6a0370a489c77ae6a332504ea0225f1d4ec0fdd2fd31f`, superseding the initial patch hash above. Production compaction.mjs remains byte-identical (`7711057e0d74c8213b44518c0697b433c5bd8289a8ee21c2aadfe29619dd9c61`). Updated test hash: `c7a0f3cb610fca7e44dde1e4de7b1acd79bc377d0174fbdc45f65a1ad90f9cc8`.

The forward fixture now clears input.token_estimate before cloning, preventing the synthetic measured anchor. For completed results it compares the same text-only context and expects a 1500 delta. This is source-plausible under pinned estimatePrompt/estimatePart and IMAGE_TOKEN_ESTIMATE=1500: the compared content arrays otherwise retain the same text and neither fixture has assistant usage. Failed results only assert finiteness, correctly avoiding a fixed image-token claim for the error envelope. This resolves the earlier measured-anchor coverage limitation as a proposed control, not as an executed result. Seven tests remain NOT RUN; all other coverage/integration limits and source-acceptable verdict remain unchanged.
