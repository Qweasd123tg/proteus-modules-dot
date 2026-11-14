# Независимый source-only review ownership SSE state

## Итоговый вывод

У двух локальных изменений не найден semantic blocker. Точный materialized before/after diff независимо прочитан и совпадает с предложенным scope. Это оправданный небольшой cleanup ownership и одинаковых веток, а не новый функциональный дефект или крупная архитектурная переработка. Source-review принятие не означает compile/test/runtime PASS.

## Anthropic state

- В stream_response state создаётся один раз; Arc не клонируется и не передаётся другому владельцу. Единственный lock расположен внутри того же stream, непосредственно перед translate.
- Сохранение `AnthropicStreamState::default()` до `async_stream::stream!` сохраняет eager создание message_id. Перенос default внутрь stream поменял бы момент генерации ID, поэтому не включён.
- translate получает `&mut self`, но возвращает owned `Vec<ModelStreamEvent>`. Вектор не заимствует state или event. Прямой mutable borrow заканчивается до итерации по mapped и до yield, как раньше завершался lock guard.
- Реальный pinned Core `41bdfffa6e70228278b4abc758b7f81a12672f35`, contracts/model.rs: ModelEventStream = Pin<Box<dyn Stream<Item=Result<ModelStreamEvent>> + Send>>. Sync для stream не требуется. Поля AnthropicStreamState, включая блоки, usage и DsmlStreamFilter, являются owned String/Vec/Value/ID и обычными числовыми/boolean полями; оснований требовать Mutex для Send здесь не обнаружено. Это source inspection, не compile-check.
- Генератор владеет state и SSE stream. В обычном drop/cancel оба освобождаются вместе с генератором; внешнего Arc владельца, требующего сохранения state после drop, нет. Mutex не выполнял межзадачную синхронизацию в этом пути.
- Terminal detection, transport-error event, malformed-event translation, EOF error и порядок событий не меняются. Poisoned-lock повторный доступ после panic не является обещанным обычным способом возобновлять этот stream; полная эквивалентность после unwinding/повторного poll не заявляется.
- Arc import нужен factory return type и Arc::new adapter, его удалять нельзя. Auth/request construction находятся вне изменения и не анализировались.

## OpenAI одинаковые arms

Оба исходных arm полностью совпадают: call_id fallback на item_id применяется только при отсутствии первого поля; потом as_str/default; delta извлекается так же; пустой ID или delta подавляет event; результат ToolCallDelta с name=None. Общий pattern для двух строк сохраняет эти детали. Не нужно менять fallback на более «умный», создавать helper или менять соседние terminal branches. В частности response.completed не удаляется.

## Пределы

Modules source прочитан напрямую на c035142558f0fca43e9772fc0e50ca293abf1531: anthropic.rs, anthropic/stream.rs, sanitize.rs, usage.rs и openai/stream.rs. Core контракт прочитан прямо на dependency pin. Проверка Send/lifetime статическая. Rust, compiler, formatter, tests, providers, project scripts/runtime и установки не запускались. Production и публикации не изменялись. PR106/107 не затрагивают эти source files; полный повторный forensic dedup не проводился.

## Финальный diff и независимый подсчёт

Проверены именно after и stream-state-and-delta.patch: единственные изменения Anthropic — импорт Mutex, обёртка state и lock block; единственное изменение OpenAI — объединение двух одинаковых arms. Default остаётся перед stream!, Arc factory остаётся. Terminal/fallback/identity semantics не редактируются; response.completed сохранён.

| Файл | Raw before → after | Nonblank before → after |
|---|---:|---:|
| anthropic.rs | 287 → 284 | 260 → 257 |
| openai/stream.rs | 183 → 162 | 178 → 157 |
| Всего | 470 → 446 | 438 → 414 |

Итого независимо подтверждены −24 raw и −24 nonblank строки. Никакого runtime/performance/memory measurement нет: удаление ненужных ownership wrappers видно по исходнику, а размер генератора и итоговая производительность не измерены. Сообщённый координатором git apply --check не повторялся и не является компиляцией.

SHA256 reviewed artifacts:

- after anthropic.rs: `27f0a341526f7d77f617796c323ff46d1c5a8d2d89e6f9bfa49ce1dbb7488f7b`
- after openai/stream.rs: `1518a04aecca5fa4852d8cbf7b268ea45bf06c60c4249efd30796168dfe31e30`
- patch: `6b21e17767502f83f68b3f8c542412a9836811bf66f15da46170d72b7a09ac14`

Полный catalog из 17 exact blobs проверен координатором; этот review отдельно проверял относящиеся к выводу исходники и точный кандидат, не повторяя весь catalog.
