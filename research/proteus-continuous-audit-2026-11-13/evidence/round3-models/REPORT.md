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

## A2. P2: Anthropic no-argument tool changes from {} to null in streaming

A `tool_use` content-block start with `input:{}` is initialized as an empty string accumulator. If the input delta is empty or omitted, finalization converts that string to `Value::Null`. Nonstreaming parsing correctly retains `{}`. Therefore changing transport changes the canonical arguments of the same completed tool call.

**Reproduction:** fixture sequence with tool-use start `{}`, empty `input_json_delta`, block stop, stop reason `tool_use`, message stop. Compare to the equivalent ordinary JSON response. Result: streaming args `Null`, JSON args `Object {}`. Both indicate a completed executable tool call. Object-schema tools can reject the null arguments; replay of that message also emits a non-object Anthropic `input`. The replay consequence follows from source inspection, not a live API rejection.

Sources:
- [Start drops input, lines 109–124](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/stream.rs#L109-L124)
- [Empty accumulator becomes null, lines 295–318](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/stream.rs#L295-L318)

Suggested correction: retain the start-block input as the fallback when no argument bytes arrive; parse the concatenated delta buffer when present. Keep empty object distinct from absent/invalid input, and cover both no-delta and empty-delta cases. Do not repair every malformed JSON response indiscriminately to `{}`.

Contract reference: [Anthropic streaming](https://platform.claude.com/docs/en/build-with-claude/streaming) specifies that the final tool-use input is an object. This is a valid fixture/contract comparison, not evidence that a live Claude no-argument call emitted this exact event sequence during this audit.

## A3. P2, conditional interoperability defect: Anthropic discards initial text

The text branch of `content_block_start` always initializes an empty buffer. Nonempty text carried in that start event is neither emitted nor retained. Deltas are then appended to the empty buffer. This differs from nonstream parsing and the provider SDK's accumulation semantics.

**Reproduction:** start text `1 + 1`, delta ` = 2`, normal end-turn. Streamed final response is `= 2`, while the equivalent JSON response is `1 + 1 = 2`. The leading space is trimmed by the existing sanitizer. The initial-text/delta scenario also appears in the official Anthropic Go SDK tests. Common streams with an empty initial text block are not affected; live-provider frequency was not measured.

Source: [text start initialization, lines 106–108](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/stream.rs#L106-L108).
Provider fixture reference: [Anthropic Go SDK message tests](https://github.com/anthropics/anthropic-sdk-go/blob/main/message_test.go), case `text content block with citations`.

Suggested correction: treat start-block text as actual content for both the incremental events and accumulated terminal message, using the same DSML/sanitization policy as subsequent deltas. Test no-delta starts and starts followed by deltas. Do not merely append text to the terminal message while leaving the visible stream inconsistent.

## Verification

- Existing model-pack library suite: **158 passed, 0 failed**, with the five added `audit_` tests filtered out. See `baseline.log`.
- Added invariants: **5 failed, 0 passed**, as expected on the defective baseline. Three test functions cover A1, one A2, one A3. See `regressions.log`.
- `git diff --check`: passed.
- Existing tests include attachment image encoding, redacted thinking round trips, truncated tool arguments, transport retry/fallback and stream completion. Their passing does not cover the new edge cases.
- No complete workspace gate, npm/Pi execution, live inference, GUI, OAuth or subscription-provider acceptance tests were performed in this pass.

Apply `regression-tests.patch` to the pinned Modules revision in an isolated copy. With the project's Rust toolchain available:
```sh
python3 scripts/test.py -p model-pack --lib -- --skip audit_
python3 scripts/test.py -p model-pack --lib audit_ -- --nocapture
```
The second command should fail until the defects are corrected. The tests do not modify production files or use live provider configuration. Local HTTP fixtures require loopback binding; set localhost/127.0.0.1 in NO_PROXY if your environment uses a proxy.

## Reading coverage

`coverage.tsv` and `coverage.json` list **25 fully read baseline files, 4569 lines**, with content hashes. These are conservative manual-reading counts, not runtime or test coverage. They exclude partial reads, setup/build files, extra tests and the pinned Core contract excerpts. Important remaining areas include Codex authentication/quota/catalog modules and other unlisted provider/support files. This was not a complete line-by-line audit of all Modules.

An early setup compilation used an ambiguous `.into()` in new test code; this was fixed in the test additions before the reported runs. Such setup mistakes are not product findings. The package contains only the final reproducible test patch and completed-run logs.
