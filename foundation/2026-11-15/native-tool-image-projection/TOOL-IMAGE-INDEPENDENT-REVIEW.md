# Независимый source review: native tool-result images A1

## Verdict

В exact candidate source-level blocker не найден. Исправляется известный A1/PR85: native OpenAI/Anthropic request serializers больше не заменяют корректный ToolContent::Image одним text placeholder. Это не OTM-1 и не новая finding. Source acceptance не означает compile/test/runtime/provider PASS.

## Production boundary

Прочитан полный diff четырёх файлов и surrounding message serializers. Единственный вызов private to_openai_input обновлён с profile.supports_image_input. Function и Freeform сохраняют прежние type/call_id и surface resolution (включая прежний default для отсутствующего call). Unsupported surface error остаётся до новой projection. Оба output paths используют один helper.

Без Image helper возвращает Value::String(result.text_or_status()), то есть прежнюю string wire shape и тот же exact text. При Image вывод начинается с единственного input_text/text, содержащего неизменённый text_or_status, затем изображения идут в исходном относительном порядке content. Error > output > content/status precedence сохраняется; картинки добавляются и при failed result. Это не сохранение interleaving каждого Text/Json/Image элемента: прежний text projection намеренно агрегирован первым. Binary не интерпретируется как изображение, даже с MIME image/png, и остаётся в прежнем text fallback при его выборе.

OpenAI при наличии Image и disabled profile явно возвращает Err до формирования payload images. Text/Binary-only results не требуют image capability. Этот gate нужен, потому что текущий Core RequestShaper проверяет только верхнеуровневый ContentPart::Image. Новый gate не является полным исправлением или расширением Core shaper.

Anthropic tool_result_block остаётся единой точкой для MessageRole::Tool (pending results) и ContentPart::ToolResult в обычном message path. Outer tool_use_id/is_error сохраняются; grouping/flush и merge соседних user messages не изменены. Image source использует base64/media_type/data; OpenAI использует data URL и detail auto. Parent отдельно подтвердил текущие official schemas для обоих Responses output union и Anthropic nested image blocks; это provenance coordinator, не live provider acceptance данного review.

## Contracts, limits и ownership

Actual pinned ToolContent::Image содержит только String mime_type/data и не имеет ImageAttachment admission/decode contract. Client ImageAttachment 5 MiB/max-input-images и filesystem ImageRef encoder не применяются автоматически. Поэтому scope честно ограничен корректными provider-compatible base64 images. Нет обещания локальной валидации, resize, ограничения суммарного request size, поддержки arbitrary MIME или animated formats. Provider limits остаются применимыми; этот patch не доказывает, что любой typed Image будет принят provider.

Новая validator abstraction или перенос client-only лимитов не требуется для узкой projection. Raw payload неизбежно копируется в owned provider JSON; borrowed iterator не клонирует весь ToolResult/ToolContent заранее. Value assignment сохраняет построенные output arrays без дополнительного json! roundtrip. Performance не измерялся, экономия памяти не заявляется. Filesystem ImageRef path и Binary не менялись.

## Compile-shape и семь proposed tests

Imports ToolContent/ToolCall/ToolResult берутся из уже используемого domain facade. Match имеет wildcard для non_exhaustive ToolContent. peekable iterator держит immutable borrow result и совместим с text_or_status(&self); mutable self/lifetime через await не добавляется. Existing image_tests modules уже подключены обоими adapters. Test freeform call использует требуемый args.input string. По исходнику новых dependency или API нет; компилятор не запускался.

Прочитаны четыре OpenAI и три Anthropic test functions. Проверяются обе OpenAI surfaces, false capability, error-over-output и content-only fallback, string shape для output/empty success/empty failure/structured content/Binary; две картинки с Binary между ними. Anthropic дополнительно проверяет обе message paths, is_error, grouping с последующим user text. Fixture сравнивает ожидаемый serializer Value, не выполняет provider requests.

Limits: tests не выполнялись; нет live provider, full model/stream/tool loop, rejected image/oversized payload или exhaustive mixed-history coverage. PNG/GIF base64 fixtures здесь используются как exact serializer inputs, не как доказательство media decoding или provider image acceptance. Отсутствие новых local validation tests соответствует заявленному scope, а не подтверждению любых image bytes.

## Evidence

Baseline Modules c035142558f0fca43e9772fc0e50ca293abf1531 / Core pin 41bdfffa6e70228278b4abc758b7f81a12672f35. Coordinator сообщил 21 verified source blobs и text apply/check. Композиция с другими PR этим review не подтверждалась; parent готовит её отдельно. Independently пересчитаны SHA256:

- patch: 25c06b57d1200568811ca9f98eb77979fadf8c08d020d5b09fe656f9aa552e33
- OpenAI request.rs: 6a10a8a3dbe37668c02101c63c373d8ebb1cb85475fac950c648a488652f05c0
- OpenAI image_tests.rs: c600d35eed35bf1bb97609f61772266a18b4f159a499e3bd409204dd8582abad
- Anthropic request.rs: 5ce3e4d87f0fd23e214a7a4bd80e711f55a49aad5999a108b82a67f60aa39d28
- Anthropic image_tests.rs: d7305a72ba5e4834bcf4ce38799043f2e4a873b8d9a56483b8b883b2364f5ec8

Rust/compiler/formatter/tests/runtime/project scripts/dependency installs не запускались; production и публикации не менялись. Это correctness projection с добавлением кода, не deletion/performance refactor.
