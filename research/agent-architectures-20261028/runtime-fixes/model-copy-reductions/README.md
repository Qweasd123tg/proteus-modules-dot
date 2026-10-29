# Четыре локальные правки владения в model-pack

База всех четырёх независимых patches: `Proteus-harness/Proteus-modules`
[`ea459a60d8fce621ccabff33ff7ff9dc9d55573a`](https://github.com/Proteus-harness/Proteus-modules/commit/ea459a60d8fce621ccabff33ff7ff9dc9d55573a).
Это `main`, прочитанный через GitHub connector 2026-10-28. Проверен также
Core head `bd4aae62c738befcdf9b3a1a831837447ecb7aad`; Core не изменяется.
Контракт request проверен по **реальной Cargo dependency** Modules:
Core `1f533a13f20a93bf164f7c8a169553b0b219bb51`, а не по случайной локальной копии.

## 1. Передать request во fallback, не клонировать

[`owned-stream-fallback-request.patch`](owned-stream-fallback-request.patch)
меняет ровно по одной строке в `adapters/openai.rs:264` и
`adapters/anthropic.rs:214`: `request.clone()` → `request`.

`CanonicalModelRequest` содержит owned history, instructions, tools, metadata.
Его derived `Clone` дублирует эти данные. Раньше это происходило при каждом
успешном открытии SSE, независимо от того, потребуется ли fallback.
Теперь тот же owned request перемещается в уже существующий stream future.

**Почему владение корректно:**

1. `stream_response` получает request по значению. До изменённой строки он
   только заимствуется для подготовки owned `serde_json::Value` request body.
   Подготовка и отправка HTTP-запроса уже завершились; body не содержит ссылок
   на request. Ниже строки нет обращений к исходному имени `request`.
2. `fallback_request` захватывается `async_stream::stream!`, как и раньше.
   Единственное потребление — `complete_response(fallback_request).await`
   в transport-error ветке. После неё безусловный `break`, поэтому вторичного
   потребления в следующей итерации нет. `yield` внутри ветки этого не меняет:
   после возобновления выполнение доходит до того же `break`.
3. Нормальный terminal, provider error, EOF, OpenAI idle timeout и отмена
   потребителем не используют request повторно: stream его освобождает.
   Ошибка до создания stream по-прежнему возвращается через `?`.
4. OpenAI `stream_error_fallback` и Anthropic fallback policy не меняются;
   сериализация, retry, число HTTP-запросов и порядок событий не меняются.
   Данные request не сравниваются и не пересобираются.

Эффект по исходнику: **один deep clone request удалён на открытый stream**
в каждом адаптере. Это устраняет временное дублирование history/tools; не
обещает освобождение request во время stream при выключенном fallback.

Источники: [OpenAI stream](https://github.com/Proteus-harness/Proteus-modules/blob/ea459a60d8fce621ccabff33ff7ff9dc9d55573a/model/model-pack/src/adapters/openai.rs#L254-L323),
[Anthropic stream](https://github.com/Proteus-harness/Proteus-modules/blob/ea459a60d8fce621ccabff33ff7ff9dc9d55573a/model/model-pack/src/adapters/anthropic.rs#L200-L267),
[owned request contract](https://github.com/Proteus-harness/Proteus-core/blob/1f533a13f20a93bf164f7c8a169553b0b219bb51/crates/proteus-contracts/src/model_standard/canonical_request.rs#L13-L29).

## 2. Передать готовую строку в OpenAI TextDelta

[`owned-openai-text-delta.patch`](owned-openai-text-delta.patch) меняет две
строки в `adapters/openai/stream_state.rs:129–134`.
После построения owned `emitted` код заимствовал `&str`, затем создавал второй
`String` через `to_owned()`. Теперь без смены content part в event перемещается
уже готовый String.

**Разбор ветвей:**

- Первый non-empty delta или продолжение той же part: до и после event
  содержит ровно `emitted`; вместо второй копии передаётся владение.
- Другая part: остаётся тот же `format!("\n{text}")`, с тем же newline и
  содержимым. Форматирование owned String вместо `&str` не меняет текст.
- Пустой `emitted`: прежний ранний возврат до `text_parts.insert` не изменён.
- `refusal.done`: suffix/replace-buffer вычисляются прежним кодом; патч
  затрагивает только последующую передачу уже вычисленной строки. Поэтому
  prefix-match, prefix-mismatch и пустой suffix сохраняют прежнее поведение.
- `message_id`, phase, порядок state updates, terminal repair и JSON parsing
  не затронуты. Старый `terminal-sse-parse.patch` не продублирован.

Эффект по исходнику: **одна лишняя String allocation/copy удалена для каждого
непустого TextDelta без переключения part**. На переключении part остаётся
прежняя allocation форматирования.

Источник: [delta branch](https://github.com/Proteus-harness/Proteus-modules/blob/ea459a60d8fce621ccabff33ff7ff9dc9d55573a/model/model-pack/src/adapters/openai/stream_state.rs#L94-L141).

## 3. Сортировать ссылки на instructions, не копии текста

[`borrowed-request-instructions.patch`](borrowed-request-instructions.patch)
меняет по две строки в `adapters/openai/request.rs:189–193` и
`adapters/anthropic/request.rs:136–140`.
`joined_instructions` клонировал весь `Vec<InstructionBlock>`, включая каждый
`text`, лишь чтобы отсортировать его и снова скопировать текст в результат
`join("\n\n")`. Теперь сортируется локальный `Vec<&InstructionBlock>`;
`join` получает `&str`, но возвращает прежний owned `String`.

**Почему результат тот же:** сохраняются исходная последовательность references,
stable `sort_by_key(Reverse(priority))`, порядок блоков с одинаковым priority,
фильтрация whitespace-only через тот же `trim`, исходные пробелы непустых блоков,
разделитель и правило `None` для пустого итога. Исходный request не сортируется
и не изменяется. Borrow заканчивается внутри синхронной функции; ссылки не
попадают в JSON, stream, cache или другой export. Это не замена snapshot на
общую изменяемую память.

Эффект по исходнику: убирается **одна промежуточная копия всего текста
instructions на каждое построение запроса** обоих адаптеров. Вектор ссылок,
сортировка и allocation итоговой строки остаются. Это относится и к длинным
system/project instructions, а не только к коротким IDs.

Источники: [OpenAI instructions](https://github.com/Proteus-harness/Proteus-modules/blob/ea459a60d8fce621ccabff33ff7ff9dc9d55573a/model/model-pack/src/adapters/openai/request.rs#L188-L198),
[Anthropic instructions](https://github.com/Proteus-harness/Proteus-modules/blob/ea459a60d8fce621ccabff33ff7ff9dc9d55573a/model/model-pack/src/adapters/anthropic/request.rs#L135-L145).

## 4. Форматировать FileRef без копирования вложенного файла

[`borrowed-file-reference-content.patch`](borrowed-file-reference-content.patch)
меняет по одной строке в тех же двух request builders.
`content.clone().unwrap_or_default()` создавал временный String со всем
содержимым файла непосредственно перед копированием в `format!`.
`content.as_deref().unwrap_or_default()` даёт заимствованный `&str`.

`content` по закреплённому контракту — `Option<String>`. Для `Some(s)` оба
варианта форматируют ровно bytes `s`; для `None` — пустую строку. Path display,
newline, Unicode, пустое `Some("")`, JSON escaping и порядок history/items не
меняются. Форматирование возвращает owned String до завершения borrow;
исходное содержимое и isolation request сохраняются.

Эффект по исходнику: **одна лишняя полная копия FileRef content удалена при
каждом включении такого элемента истории в запрос**. Форматирование и
существующая JSON serialization остаются; их копии патч не объявляет устранёнными.

Источники: [OpenAI FileRef](https://github.com/Proteus-harness/Proteus-modules/blob/ea459a60d8fce621ccabff33ff7ff9dc9d55573a/model/model-pack/src/adapters/openai/request.rs#L430-L438),
[Anthropic FileRef](https://github.com/Proteus-harness/Proteus-modules/blob/ea459a60d8fce621ccabff33ff7ff9dc9d55573a/model/model-pack/src/adapters/anthropic/request.rs#L257-L264),
[FileRef contract](https://github.com/Proteus-harness/Proteus-core/blob/1f533a13f20a93bf164f7c8a169553b0b219bb51/crates/proteus-contracts/src/model_standard/content_part.rs#L104-L107).

Во втором проходе не менялись необходимые копии ToolCall в отдельных owned
`message.parts` / `response.tool_calls`, provider metadata и схемах outgoing
JSON. Замена сериализации root JSON либо порядка его ключей тоже не делалась.

## Что проверено и что не запускалось

- Базовые пять файлов прочитаны по фиксированному commit через GitHub connector;
  их bytes сверены с Git blob SHA из connector (`source-pins.json`).
- Просмотрены полные затронутые функции, контракт request, request-body builders,
  текущие AGENTS/README/Cargo и имеющиеся stream tests.
- Статически проверены diff/whitespace и применимость каждого patch через
  `patch --dry-run --batch -p1` к точным базовым файлам. Это не runtime tests.
- **Сборки, tests, benchmarks и CI не запускались** по поручению пользователя.
  Скорость, RSS и число allocator calls не измерялись; компиляция не заявляется.
- Имеющиеся сценарии для дальнейшей локальной проверки: `translate_sse_text_delta`,
  `empty_completed_output_recovers_streamed_text_in_adapter`,
  `refusal_delta_done_and_terminal_preserve_visible_text_and_metadata`,
  `stream_trace_plain_text_emits_deltas_and_final_response`.
  Они просмотрены, но не считаются выполненными или полным покрытием fallback.

Исходные файлы закреплены ссылками и Git blob SHA в source-pins.json. Патчи можно применять независимо. Upstream и рабочие копии пользователя не изменены; здесь опубликованы исходниковые patches.
