# Anthropic SSE: стартовый блок как часть накопленного содержимого

## Статус и границы

**Source-only fix candidate известных A2/A3, не новая finding и не проверенное runtime-исправление.**
Предшествующий отчёт находится в [PR85, round3-models](https://github.com/Qweasd123tg/proteus-modules-dot/blob/51b99b01b15fc1696f1d5bc58101610581791d0b/research/proteus-continuous-audit-2026-11-13/evidence/round3-models/REPORT.md).
Его прежние динамические результаты здесь не повторялись.

- Modules main повторно проверен: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Фактическая Core dependency Modules: `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Delivery main: `51b99b01b15fc1696f1d5bc58101610581791d0b`, после публикации PR111.
- Изменения только в отдельной текстовой копии. Upstream production, refs, dependency pins и binaries не менялись.
- Rust/compiler/rustfmt/clippy, тесты, provider/HTTP/process runtime, project scripts и dependency install **не запускались**.

## Общая причина двух потерь

В `model/model-pack/src/adapters/anthropic/stream.rs` старт `text` создаёт пустой накопитель, а старт `tool_use` сохраняет лишь id/name и пустую строку JSON. Содержимое стартового события не является частью начального состояния для этих двух вариантов.

1. A2: `input: {}` без последующих непустых JSON-фрагментов становится `Value::Null` при финализации. Nonstream parser сохраняет исходный объект. Это влияет на аргументы завершённого вызова; изменение transport меняет DTO.
2. A3: начальный `text` теряется и в TextDelta, и в итоговом сообщении. Пример `1 + 1` в start и ` = 2` в delta даёт неполный ответ. Обычные пустые starts не затронуты; частота такого ответа у живого провайдера не установлена.

Проблема не решается заменой всех пустых аргументов на `{}`: missing/null и malformed nonempty JSON нужно по-прежнему различать. Не решается и добавлением start text только в terminal response: тогда видимый поток остаётся неполным.

## Предложение без нового framework

`anthropic-start-blocks.patch` изменяет один production-файл и добавляет отдельный test module.

- **Text:** существующая последовательность `DsmlStreamFilter → block buffer → TextDelta` извлечена в private `append_text`. И стартовый text, и последующий text_delta используют именно её. Старт обрабатывается после установки блока. Пустой start по-прежнему не создаёт событий. Существующие message_id, phase, final sanitization и даже поведение delta с отсутствующим/несовпадающим block index не меняются.
- **Tool input:** один дополнительный typed `initial_input: Value` сохраняет input стартового блока. Если JSON-байтов не было, финализация перемещает именно это значение. Отсутствующее поле остаётся Null, как в существующем nonstream parser. Empty JSON deltas не отменяют fallback.
- При первом непустом JSON-фрагменте initial input больше не нужен и освобождается. Накопленные фрагменты разбираются как **замена**, не concatenation сериализованного start input и не object merge. Ошибка JSON, включая whitespace-only buffer, остаётся ошибкой; fallback не маскирует её.
- Отсутствие `tool_use` stop reason по-прежнему исключает executable tool calls до разбора аргументов. Length/Unknown, reasoning/opaque, usage, errors/retries и новые типы provider events не расширяются.

Публичные DTO, traits, зависимости и provider contracts не меняются. Это устранение двух пропущенных initial-state ветвей через существующий stream accumulator, не общий потоковый framework и не рефактор ради уменьшения строк.

### Стоимость и ownership

Стартовое input Value копируется из краткоживущего parsed event, потому что accumulator должен владеть им после `translate`. Оно живёт до непустой JSON-дельты, финализации или drop stream state; при fallback переносится без дополнительной копии. Это дополнительное удержание исходного input, ранее ошибочно отброшенного. Новый общий bytes budget не вводится; ограниченность памяти всего потока не заявлена.

В production prefix `stream.rs` 342 → 371 строк (+29, включая комментарии и разделитель перед test registration). Путь DSML filter/buffer/event остаётся один, теперь с двумя call sites. Ускорение, RSS/allocations и снижение общей complexity метрикой не измерялись.

## Первичные источники

[Anthropic streaming docs](https://platform.claude.com/docs/en/build-with-claude/streaming) описывают start, произвольное число delta и stop для content blocks, а JSON delta являются частями нового input. Документация проверена 2026-11-15.

[Официальный Python SDK, exact SHA, accumulate_event](https://github.com/anthropics/anthropic-sdk-python/blob/5139cf2e7d07aa618a6c30b7e0c712f10ccb5ad9/src/anthropic/lib/streaming/_messages.py#L443-L522) сохраняет start block, дописывает text и ведёт отдельный JSON buffer с нуля; input заменяется только при непустом buffer. Именно эта семантика, не предположение о частоте live replies, лежит в основе proposal.

[Официальный Go SDK test, exact SHA](https://github.com/anthropics/anthropic-sdk-go/blob/eba55420edf6d9ee276722cf7b6d001c602ff44d/message_test.go#L281-L299) содержит начальный text `1 + 1` и следующий delta ` = 2`. Это fixture/совместимость, не live-provider measurement. Соседний Go no-params fixture для доказательства A2 не используется.

## Предлагаемые regression tests: NOT RUN

Новый `anthropic/stream/start_tests.rs`, шесть чистых source-level test definitions:

1. Text start без delta, с empty delta, с продолжением, Unicode и обычный empty start. Проверяется порядок TextDelta, его identity, итоговые payloads и nonstream parity.
2. Один DSML marker, разделённый между start и delta, и целый фильтруемый start. Общая filter state не обходится.
3. Initial tool input `{}`, непустой объект, explicit null и absent field при 0/1/2 empty deltas. Сравниваются exact ToolCalls и canonical payloads с nonstream parser. Synthetic JSON delta из fallback не создаётся.
4. Непустые фрагменты заменяют initial object, а не merge/append. Existing ToolCallDelta bytes сохраняются.
5. Malformed/whitespace nonempty JSON остаётся typed Other failure, без успешного Response и без подстановки initial input.
6. max_tokens, end_turn и unknown stop reason не делают initial tool call executable, даже при незавершённом JSON buffer.

Это не провайдерные/HTTP/process tests. Не доказаны end-to-end replay, workflow execution, cancellation или исчерпывающая эквивалентность всех malformed event sequences. Existing trailing DSML flush и final trim не меняются; утверждения, что любые streamed bytes теперь равны terminal text, нет.

## Текстовая проверка и композиция

- 15 source blobs из `SOURCES.json` совпали по Git blob SHA; SHA256 в `READ-VERIFICATION.json`. Это проверка identity скачанного текста, не покрытие выполнения или утверждение, что каждый вспомогательный файл прочитан целиком.
- `git apply --check --whitespace=error` прошёл. Применение patch в inert text copy дало exact `after` bytes.
- PR108 + новый patch: оба порядка прошли и byte-equal.
- PR110 + новый patch: оба порядка прошли и byte-equal.
- PR108 + PR110 + новый patch: три порядка прошли и byte-equal **с уже опубликованным `anthropic-failure-on-PR108.patch`**. Исходный известный conflict PR108/PR110 этим не отменяется.
- M4 classification/error branch и PR108 eager state ownership в combined copy сохранены. Exact independent review без source-level blockers: `START-BLOCK-INDEPENDENT-REVIEW.md`.
- PR111 относится к Core `Model::complete`, не к этим файлам; межрепозиторная сборка/интеграция с ним не проверялась, Modules pin не обновлён.

`COMPOSITION.json` сохраняет все семь порядков и четыре сравнения; `PATCH-VERIFICATION.json` сохраняет hash и byte-check. Эти проверки не означают compile/test/CI PASS. До применения upstream нужны соответствующие project gates и runtime regressions в штатной среде.

Patch SHA256: `bdd344667c3dc3645487d6dd953032b46214c22ae8515a8eef2122a351f3213e`.
