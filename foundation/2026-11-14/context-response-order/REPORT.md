# DS-8: порядок warm model-context отличается от canonical response order

**P3 source-only live/canonical consistency candidate либо уточнение контракта.** Область: concurrent custom workflow внутри одного resident root invocation. Не утверждаются потеря total usage, неверная физическая хронология provider responses, проявление в default profile или persistent next-turn corruption.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87 → PR88 → PR89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. Позднейший upstream требует повторной проверки. Production не менялся; Rust/runtime/HTTP/replay/tests не запускались. Абстрактная Python-модель порядка операций не является Tokio simulation/runtime evidence и не включена в пакет.

## Две проекции одних завершённых фактов

`proteus-contracts/src/contracts/workflow_context.rs:3–10` описывает ordered model-context facts, где Usage.last_tokens относится к последнему response группы. `docs/architecture/process-module-architecture.md:499–510` описывает реконструкцию этих facts из canonical records. Для concurrent calls «последний» может означать provider arrival, commit либо caller delivery. Этот отчёт не выбирает физическую хронологию: обнаружено расхождение двух не помеченных как разные представлений.

- `core/model_context.rs:47–67`: response удаляет известный request, суммирует input/output в total_tokens и заменяет last_tokens. Разные A/B некоммутативны по last_tokens, но total двух successful responses одинаков.
- `core/model_context/projection.rs` применяет root-owned records в journal order. `session_journal/storage/append.rs` обновляет projection только после успешного commit под writer mutex; strict cold read использует ту же projection.
- [`ContextExecutionRecorder`:78–88](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/model_context/recorder.rs#L78-L88) сначала await-ит inner model_response_recorded, затем отдельно берёт warm context lock и применяет response. Lock не охватывает durable append, canonical sequence для второго fold не передаётся.
- `core/runtime/execution_binding.rs` оборачивает root SessionExecutionRecorder этим recorder с общей session.model_context. Resident `runtime/conversation.rs:36–55` возвращает warm snapshot; cold/store snapshot складывается из journal.

## Source-derived successful interleaving

Оба различных root requests A/B уже зарегистрированы в обеих проекциях. Свежая группа: A=11 tokens, B=22; нет compaction, overflow, cancellation, hooks или failed I/O.

1. A commits response в journal, но его outer awaiter ещё не продолжен.
2. B commits после A: canonical total=33, last=22.
3. B outer recorder первым применяет response к warm context.
4. A outer recorder применяет response позже. Оба recorder calls успешно завершаются: warm total=33, last=11.
5. Пока workflow остаётся resident до завершения turn, live conversation snapshot может вернуть last=11, strict store projection last=22. History revision при model responses может оставаться прежней.

Проверенный partial order: `durable(A) < durable(B) < warm(B) < warm(A)`. [`writer.rs:115–133`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store/writer.rs#L115-L133) передаёт owned writer guard в spawn_blocking. Worker освобождает guard до того, как async caller обязан возобновиться. Поэтому B может commit и publish раньше outer A; вывод не требует воображаемого yield внутри синхронного выражения. Это source reachability, не выполненная репродукция и не оценка вероятности scheduling.

## Concurrent custom workflow и ограничения

Model/recorder интерфейсы Send+Sync и async &self, BoundModel создаёт distinct exchange IDs и не имеет общего serialization mutex для всех model calls. Root calls используют общий wrapped recorder. Custom workflow может poll-ить два вызова одновременно; occurrence в shipped Modules/default profiles не установлен.

[`WorkflowHostRuntime::complete_model`:135–152](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/workflow_host.rs#L135-L152) берёт shared operation_gate.read, а dispatcher `process_adapters/workflow.rs:145–153` создаёт отдельные futures. Single-active-stream ограничение ModelStreams не следует переносить на два complete calls. Session run_lock тоже не сериализует calls внутри одного уже admitted root.

Live HTTP `/conversation` имеет путь к resident context (`http/sessions.rs:196–213`), но реальный HTTP/socket/GUI симптом и downstream policy decision не воспроизводились. Нельзя считать это потерей provider accounting: SessionUsageSnapshot использует canonical projection, total в приведённом двух-response случае одинаков.

Normal `run_reserved_chain` вызывает release_history (`runtime/turn.rs:150`), сбрасывая resident context; next-turn binding восстанавливает canonical prefix (`execution_binding.rs:26–32`). Поэтому witness требует сохранить workflow resident после обоих calls до final completion. Неверный next-turn budget, durable counter, duplicate provider work или бесконечное рассогласование не доказаны.

## Proposed regression, НЕ РЕАЛИЗОВАН И НЕ ЗАПУЩЕН

1. Test wrapper вокруг настоящего SessionExecutionRecorder сигналит после durable response A append, но до возврата acknowledgement. Снаружи находится настоящий ContextExecutionRecorder. Сначала записать оба valid distinct requests.
2. Запустить A до post-inner gate; завершить B; отпустить A; дождаться обоих successful calls. Сравнить warm context со strict canonical projection.
3. Desired invariant после выбранного ordering contract: представления согласованы либо различие order semantics явно выражено API. Current observational oracle last=11 против last=22 не является PASS исправления.
4. Sequential A→B control должен быть согласован. Затем отдельная custom root workflow integration fixture с двумя shared bound-model calls доказывает полный capability path и удерживает resident turn до assertions.
5. Проверить normal release/next-turn canonical recovery и неизменность total canonical usage отдельно. Не использовать sleep как proof. Existing before-write append pause не является нужным post-inner/pre-return gate.

## Упрощение без готового patch

Выбрать один ordered source для persisted context publication. Canonical writer уже складывает facts; второй warm fold главным образом нужен no-store execution. Возможны чтение committed context от одного authority либо явная commit-sequence ordering публикации. No-store поддержку сохранить отдельно: у неё нет независимого canonical order.

Не держать context mutex через writer I/O без анализа: readers/checkpoints уже сочетают history/context/writer locks, механическое усиление lock scope может дать цикл. LOC/RSS/latency и частота ошибок не измерены.

## Independent review и дедупликация

Независимый review подтвердил recorder/projection/binding/writer/BoundModel/host/reader цепочку и достижимость same-root custom concurrent complete calls. Ограничения про resident turn, distinct ordering meanings и normal release включены.

Автор прочитал полные model_context/tests.rs, session_journal/context_tests.rs и session_store/usage_tests.rs; reviewer также прочитал HTTP tests/conversation.rs. Они покрывают sequential accounting и live/cold parity после completed boundary, но просмотренные tests не создают reversed acknowledgement schedule. Тесты не запускались; exhaustive coverage audit не заявляется.

Targeted PR84 extracted-text search и опубликованные round3-core, hook-usage, resume-integrity не выявили совпадения причины. Ближайший hook-usage относится к missing request-estimate attribution, не к этому response order. Это ограниченная дедупликация, не полный просмотр всех отчётов. DS-8 не повторяет DS-5 mixed clear revision или DS-7 compaction cardinality.
