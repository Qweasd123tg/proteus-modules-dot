# Independent bounded media-bridge contract review

Verdict: feasible minimal bidirectional bridge; no design-level reason to HOLD. Two private helpers in existing compaction.mjs are sufficient. This remains known OTM-1, not a new finding. No patch or project runtime was executed by this reviewer.

Read current Modules nativeContext/canonicalPrompt and files producer, pinned upstream 527f0b931d1f9b3ebd34e106c51b31ce5db5b075 Tool.Content, AssistantTool, ToolResultValue, to-llm-message, tool-history normalization and compaction projection. Coordinator catalogs 8 Modules + 8 upstream exact blobs; this review is source semantics, not independent remote-ref verification or installed-package verification.

## Minimal supported contract

Forward canonical result.output remains the first native text block, even when empty; content text blocks remain text, inline image blocks become Tool.Content file {uri: data:<mime>;base64,<data>, mime}. Existing files.mjs already converts such native producer attachments to canonical image, so no producer rewrite is needed. Preserve image/* MIME and base64 payload without inventing a four-format provider allowlist. This is representation support for valid inline images, not provider acceptance, base64 validation, resizing or new limits. Unsupported binary/PDF and non-inline files should not silently stringify.

Reverse must recognize the actual upstream shapes: completed single-text results become type:text; multiple blocks become type:content; failed durable tools become type:error with value {error, content}. Decode the content array, keep call id and failed status, and extract error.message for that known envelope. Removing only the forward guard would leave the callback losing typed media through JSON.stringify.

Move content[0] into canonical output ONLY if that first element is text. Never search forward for the first text after an image: that would reorder image→text into text→image. If the array starts with a file, output='' and preserve all blocks in ordered content. Empty arrays similarly yield empty output/content. Single-text legacy result retains its existing text projection.

ToolResultValue.error and text/json values are Unknown in the schema; normalization can synthesize error strings. Keep the existing sensible scalar/JSON fallback for non-envelope errors rather than assuming all error values have content/error.message. An unsupported file within a recognized typed envelope should remain an explicit failure, not fall through to JSON/base64 text serialization.

## Intentional limits and changes

Typed reverse normalization for all content arrays is preferable to a media-only branch: it gives one clear shape rule. It intentionally changes existing multi-text callback output from a JSON-array string to output plus ordered ToolContent text. Document and test that prompt representation change; do not claim byte-identical model requests. This does not rewrite canonical durable history.

The boundary is ordered model-visible text/image projection and failed/error semantics, not exact restoration of the original ToolResult DTO. Upstream can filter empty text; original failed error:null already falls back to output; filenames, metadata and output/content partition cannot be promised unchanged through arbitrary upstream normalization. Error-first text_or_status consumers may prefer error over output, so avoid claiming every downstream provider renders all failed-result text just because the DTO retains it.

Pinned compaction deliberately flattens media away when reducing requests. Preserve that policy; do not claim images always reach every summary attempt. Error envelopes also have different estimator treatment from content arrays, potentially including serialized base64. No estimator equivalence, complete error-token coverage or full workflow runtime compatibility is established by this bridge design.

Required later source/test controls: output+text+image order, empty output, image-first native content, scalar text, multi-text normalization, known error envelope with content, scalar error fallback, image MIME/data identity, unsupported binary/non-inline rejection, and both normal workflow continuation and compaction callback boundaries when dependencies permit. Tests of extracted helpers alone must not be labeled pinned full-service execution.
