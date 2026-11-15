# Proteus model adapters: serializer and streaming review

Reviewed Modules revision: `3270dc0f894eaf4d0360306052b806099b8f5351`.
Remote `Proteus-harness/Proteus-modules` main was checked again after reproduction and still matched.
Modules' pinned Core contract revision is `b5fac84245b075896c24763b3aebac79b4375c2e`, not the separately reviewed current Core main.
Verification finished 2026-11-13 UTC. Previous Modules M1–M4 and the Desktop/Extensions round-two reports were compared; the findings below are additional.

Only test code was appended to an isolated review checkout. No production modifications, commits, PRs or publication. All tests used synthetic values. No real provider requests, keys or OAuth were used. The HTTP test used `127.0.0.1` and the literal `local-fixture-only` key.

## A1. P2: native provider requests silently discard image tool results

The OpenAI Responses and Anthropic Messages serializers reduce the complete `ToolResult` to `text_or_status()`. That method returns `output`/`error` before examining structured content; even when output is empty, an image becomes a textual placeholder rather than its bytes.

A legitimate producer exists in this repository: Pi tools move text to `output` and retain image data in `content`. A read-image/screenshot result used with a native model-pack provider therefore loses the visual input, despite the model supporting images. The request succeeds and can lead the model to answer from only the accompanying text. The Pi model serializer preserves image content; this is not a claim that Pi-to-Pi or user image attachments are broken.

**Reproduction:** two direct serializer regressions and a real-client HTTP-boundary regression. Build a ToolCall plus ToolResult containing `output="Read image file [image/png]"` and a valid base64 1x1 PNG in `ToolContent::Image`. Explicitly enable `supports_image_input`, run the actual RequestShaper, send through each production client to a local fixture server, and inspect its captured request. Both providers send only the text. No base64 image data reaches either server.

OpenAI body excerpt:
```json
{"type":"function_call_output","call_id":"read-1","output":"Read image file [image/png]"}
```
Anthropic body excerpt:
```json
{"type":"tool_result","tool_use_id":"read-1","content":"Read image file [image/png]","is_error":false}
```

Sources:
- [OpenAI serialization, lines 401–416](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/openai/request.rs#L401-L416)
- [Anthropic serialization, lines 319–325](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/request.rs#L319-L325)
- [Pi tool producer, lines 34–48](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/pi-tools/adapter.mjs#L34-L48)
- [Pinned text_or_status implementation](https://github.com/Proteus-harness/Proteus-core/blob/b5fac84245b075896c24763b3aebac79b4375c2e/crates/proteus-contracts/src/domain/tool.rs#L149-L195)

Suggested correction: serialize supported structured tool content to provider-native blocks, preserving output text and call association. OpenAI Responses supports image items in the function-call output content list; Anthropic tool-result content supports image blocks. Explicitly reject unsupported structured content rather than silently losing it. Add request and actual-wire tests for image-only and text-plus-image results.

Provider references: [OpenAI create response](https://developers.openai.com/api/reference/resources/responses/methods/create), [Anthropic handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls).
