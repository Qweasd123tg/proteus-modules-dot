# A1: сохранять изображения в native tool-result serialization

## Статус и границы

**Source-only candidate для известной A1 из PR85/round3-models, не новая находка.**
Исправляет потерю корректных inline images при подготовке запросов native OpenAI
Responses и Anthropic Messages. Это не подтверждение компиляции, прохождения
тестов, HTTP-wire интеграции или приёма запросов реальным провайдером.

Проверенные refs на 2026-11-15:
- Modules main: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Фактический Core dependency Modules: `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Отдельно наблюдавшийся Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Delivery main: `1733c1dff4d2006db0cafd6ad77288e5d34b1f8e`.

Upstream production, dependency pins, transport, Core DTO и общие validation
правила не меняются. PR108–112 остаются отдельными некомпилированными candidates.
OpenCode OTM-1/PR102, attachments transport и skills admission HOLD не решаются.

## Причина и существующий путь

`tool/pi-tools/adapter.mjs::toToolResult` переносит текст в `output`, сохраняя
inline image в `content`. На native boundary оба adapters вызывают только
`ToolResult::text_or_status()`: непустые error/output скрывают content; без них
Image превращается в placeholder, не содержащий image bytes. Pi model mapper
отдельно сохраняет Image. Пользовательские `ImageRef` обрабатываются другими
ветками и не являются причиной A1.

Ранее опубликованный A1 включал собственную проверку на старой версии. Её
результат сохранён отдельно в `PRIOR-A1.md` только как provenance/dedup; он не
считается выполненным тестом этого candidate или свежего SHA.

## Выбранное минимальное изменение

1. Нет `ToolContent::Image`: прежний `text_or_status()` передаётся строкой,
   прежние error/output/structured fallback/empty-status semantics сохраняются.
2. Есть Image: первый provider-native text block содержит **точно прежний**
   `text_or_status()`, затем идут реальные Image в исходном image-порядке.
   Это намеренно не полное переупорядочивание Text/Json/Image и не новый контракт
   всех structured blocks. Image-only placeholder остаётся вместе с image.
3. OpenAI использует один output builder для function и custom tool outputs.
   Call association и выбор surface сохраняются. Существующий model profile
   `supports_image_input=false` теперь явно отклоняет nested images до их
   data-URL allocation вместо тихого удаления. Это локальная native проверка,
   не изменение Core RequestShaper: тот по-прежнему видит только верхнеуровневые
   `ContentPart::Image`.
4. Anthropic меняет существующий `tool_result_block`, уже общий для role Tool
   и inline ToolResult. Сохраняются `tool_use_id`, `is_error`, grouping сообщений
   и положение tool result. Новый общий framework и публичный API не добавлены.
5. Binary не становится Image даже при MIME `image/png`; Json, Binary и прочие
   content сохраняют прежнюю текстовую политику. Error с image сохраняет
   приоритет error-текста, при этом image больше не исчезает.

По текущей официальной [Responses schema](https://developers.openai.com/api/reference/resources/responses/methods/create)
отдельно проверены `function_call_output` и `custom_tool_call_output`: оба
допускают строку или массив text/image/file content; image data URL допустим.
Официальный [Anthropic tool-result contract](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
допускает строку или вложенные content blocks, включая base64 image.
Эта документация подтверждает форму mapping, а не live-доступность конкретной модели.

## Лимиты и стоимость

`ToolContent::Image` в фактическом Core pin содержит только `mime_type` и `data`
как строки. Он не является `ImageAttachment`, чей `decode` проверяет 5 MiB,
base64 и magic/MIME, и не наследует `MAX_INPUT_IMAGES=4`. Filesystem helper
`adapters/images.rs` работает с `ImageRef`, не с tool inline bytes.

Candidate передаёт корректные provider-compatible base64 данные без
decode/re-encode, resize, файловых операций, URL download или новых произвольных
caps. Он **не валидирует** base64/MIME, размеры, image count, dimensions и общую
request size. Провайдер может отклонить некорректный/слишком большой payload.
Его ограничения зависят от endpoint; например [Claude vision](https://platform.claude.com/docs/en/build-with-claude/vision)
считает image limits и для nested tool results/history, а не только user images.
Нельзя выдавать attachment cap за действующий tool-result cap.

Сохранение прежде потерянных image bytes увеличивает реальный wire/request
объём. Serializer заимствует canonical result, поэтому provider Value получает
собственную строку base64 (Anthropic) или data URL (OpenAI); эти данные живут
вместе с request. Готовые arrays/strings перемещаются в envelope, без дополнительной
пересериализации большого Value через `json!`. Изменения RSS/CPU/latency не измерялись.

## Evidence и предложенные regressions

- `SOURCES.json` / `READ-VERIFICATION.json`: 21 точный upstream blob, все Git
  blob hashes совпали. Это проверка byte provenance, не execution coverage.
- `native-tool-image-projection.patch` (before/after copies used locally, not published): две production и
  две existing test files. Production 863 → 926 строк (+63); tests 84 → 304
  (+220). Цель не сокращение LOC: устранение lossy flattening на двух native
  boundaries. В OpenAI два одинаковых output envelope builders сведены к одному.
- Семь новых `#[test]` предложены, **не запущены**: both OpenAI surfaces;
  both Anthropic message paths/grouping; две images и порядок; output+image;
  error+output+image; content-only image; unchanged string/text semantics без
  image; Binary c image MIME не маппится; disabled OpenAI image capability.
- `PATCH-VERIFICATION.json`: только `git apply --check` и text apply в отдельную
  копию, затем byte comparison четырёх after files. Проектный код не запускался.
- `COMPOSITION.json`: 10 text-only orders с PR108, PR110, PR112; обратные пары и
  четыре положения A1 в совместной последовательности дают одинаковые bytes.
  Совместные последовательности используют уже существующий `110-on108` rebase:
  исходный конфликт PR108/110 этим не объявляется исчезнувшим. PR111 меняет Core,
  не обновляет фактический Modules dependency и не является проверкой integration.
- Независимое exact source review: `TOOL-IMAGE-INDEPENDENT-REVIEW.md`.

Rust/cargo/rustfmt/clippy, проектные scripts/tests, provider requests и process
runtime в этом pass **не выполнялись**. До принятия исходников нужны доступный
toolchain, форматирование, компиляция model-pack и targeted serializer/actual-wire
regressions на выбранном Core pin. При проверке live provider нельзя считать
API schema гарантией для произвольного compatible endpoint или subscription backend.
