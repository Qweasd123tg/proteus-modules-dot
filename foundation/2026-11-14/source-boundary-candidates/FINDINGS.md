# Source-only boundary findings

Точная база, статус evidence и дедупликация: [README](README.md). Все номера строк ниже относятся этому дереву. Сокращённые пути `core/...`, `app_server/...`, `process_adapters/...` относительны `crates/proteus-core/src/`.

## DS-1: disposable cache становится условием доступности history API

**P2 candidate.** Канонический journal может оставаться валидным, но вспомогательный предел fingerprint блокирует производные read API. Это не доказательство повреждения journal или потери данных.

### Цепочка по исходникам

1. [`SourceFingerprint::read`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store/read_cache.rs#L84-L107) перечисляет все записи `blobs/`, а не только referenced blobs. На 8193-й записи при лимите 8192 возвращает `None`; нессылаемые regular files, включая orphan временные файлы, расходуют тот же лимит.
2. `core/session_store/read_cache/sqlite.rs:39–40` требует fingerprint до открытия существующего SQLite snapshot. Отказ открыть Reader не означает, что SQLite повреждён.
3. `app_server/read_model.rs:120–125` допускает strict journal fallback. `core/session_store/read_model/incremental.rs:114–122` может вернуть валидированную полную проекцию с `cursor: None`, если cache publication не удалась.
4. `app_server/read_model.rs:66–117`: page → rebuild_transcript требует тот же fingerprint; `history source cannot be fingerprinted` отображается в HTTP 400 (`app_server/http/reads.rs:26–34`).
5. `app_server/read_model.rs:229–235` и `core/session_store/read_model/sqlite/tool_state.rs:13–40,92–104`: tool-state load/rebuild также требуют fingerprint. Получается `ToolStateNotReady`/HTTP 409 с предложением refresh, который не снимает постоянное физическое условие.
6. `core/session_store.rs:270–271` и `writer.rs:279–307`: clear добавляет `HistoryMutated::Replace`, но не удаляет старые journal blobs. Поэтому пустая текущая conversation сама по себе не снижает число записей. Audit-preserving clear не следует заменять удалением referenced blobs.

### Active и cold history различаются

Нельзя обещать, что полный HTTP `/history` всегда работает. Cold strict projection остаётся возможной, но active publisher может сохранять прежний paged cursor с `before > 0`. Тогда [`app_server.rs:315–334`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server.rs#L315-L334) вызывает `transcript_at_revision` и попадает в fingerprint-gated rebuild. Такой active history также может отказывать до настоящего full publisher refresh. Валидность canonical data не гарантирует успех каждой live API ветки.

### Условия достижимости и связь с PERSIST-2

Ранние ошибки `write_all`/`flush`/`sync_data` в `core/session_journal/storage.rs:272–298` могут оставлять временные файлы. Это уже известный PERSIST-2, не новая ошибка writer. Новый вывод: orphan inventory способен отключить производные API, хотя canonical readers его не гидратируют.

Порог достижим и нормальными уникальными blobs. При штатном externalization threshold 256 KiB для 8193 таких blobs требуется порядка 2 GiB; orphan entries могут снизить требуемый объём. Не заявляется типичность для короткого чата. Лимит 8192 документирован (`docs/guides/runtime-and-events.md:1406–1411` результирующего дерева). Если это сознательный product hard limit, требуется прежде всего явный контракт отказа, а не автоматическое объявление бага.

### Предлагаемый boundary regression, НЕ ЗАПУЩЕН

1. Создать изолированную валидную session с >50 transcript rows и хотя бы одним принятым tool. Отдельно проверить cold projection и active publisher с paged cursor.
2. Добавить test-owned synthetic unreferenced regular files, доведя inventory до 8192. **Выполнить strict refresh и получить новый cursor/revision**, затем зафиксировать успешные page/tool-state controls. Иначе изменение directory stamp будет ошибочно принято за эффект лимита.
3. Добавить только 8193-й файл. Проверить canonical read отдельно от active `/history`; page и tool-state проверить независимо. Зафиксировать, что содержимое существующего SQLite не изменилось, хотя Reader не открывается.
4. Проверить refresh при сохраняющемся пороге и обе history ветки. Не считать сохранённый старый cursor равнозначным full publisher refresh.
5. Выполнить штатный clear: canonical conversation пустая, inventory неизменён, физическая причина отказа остаётся.
6. Удалить только test-owned 8193-й файл. Выполнить refresh и получить **новую revision**; старый cursor не обязан ожить после смены directory stamp. Проверить восстановление новых запросов. Настоящие journal blobs не удалять.
7. Отдельный тест referenced-blob пути нужен для доказательства stock writer сценария; допустим test-only уменьшенный threshold вместо генерации гигабайтов. Не смешивать этот тест с synthetic orphan inventory.

### Направление упрощения, не реализованное исправление

Разделить canonical read revision и возможность построить disposable cache. Один validated projection result может обслуживать full/page/tool-state fallback; ошибка cache не должна автоматически становиться бесконечным refresh-needed. Рассмотреть существующий `JournalReadCursor` (`storage/read.rs:26–36`), но только с проверкой referenced blob SHA/DTO и source-race controls, а не с заменой на size/mtime. Typed permanent-unavailable reason может быть честнее дорогого fallback; стоимость и admission нужно выбрать явно. Простое увеличение 8192 лишь перемещает порог. RSS/latency не измерены, Desktop consumer не воспроизведён.

## TC-1: inner call_id не сверяется с invocation

**P2 conditional candidate.** Ошибочный или не использующий Rust SDK process worker способен вернуть `ToolResult` с ID другого вызова. JSON-RPC response identity и inner tool call identity являются разными проверками.

### Проверенная цепочка и ограничители

- [`process_adapters/tool.rs:116–142`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/tool.rs#L116-L142) декодирует и возвращает result, не сравнивая `result.call_id` с `call.id`.
- `process_adapters/client.rs:295–313` выполняет deserialization, не эту семантическую проверку.
- [`core/bound_tools/invocation.rs:91–129`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_tools/invocation.rs#L91-L129) принимает `Ok(result)` и направляет его в finish; `hooks.rs:92–129` не валидирует соответствие ID. Detached binding (`core/bound_tools.rs:42–51`) использует Noop recorder, поэтому journal не является обязательной последней защитой.
- Rust SDK проверяет это в `crates/proteus-module-sdk/src/tool.rs:140–152`. Защита SDK не гарантирует host invariant для других wire producers.
- **Journal имеет реальную защиту:** `core/session_journal/projection.rs:391–420` проверяет lifecycle, execution/thread/turn, а `storage/append.rs:100–101` отвергает invalid fact до append. Неизвестный, завершённый или чужой execution ID не означает silent corruption.
- `ExecutionFactOwner` (`projection.rs:55–59`) содержит execution/thread/turn, а не identity текущего invocation. Условный оставшийся риск: другой уже resolved, ещё не finished parallel sibling в том же execution/thread/turn может пройти эту проверку. Reachability выведена из исходников, **не подтверждена runtime-прогоном**.

### Предлагаемые regression contracts, НЕ ЗАПУЩЕНЫ

1. Worker корректно проходит initialize/list и возвращает правильный JSON-RPC response ID, но inner invoke result для A содержит `call_id=B`.
2. Detached bound tool: ожидать явную ошибку, связанную с A, а не успешный result B. Проверить, что ошибочный identity не проходит к AfterTool/recorder.
3. Journal path: разрешить параллельные A/B до barrier, пока оба resolved и neither finished; вернуть переставленные inner IDs. Проверить отсутствие misassociation до hooks/durable append. Отдельные controls: unknown ID отклоняется; корректный ID принимается.

Предпочтение: одна обязательная host validation на общей границе tool execution до hooks/recording. Не переписывать ID молча: это скрывает дефект producer. Не вводить SDK-specific исключение. Изменения production и security escalation здесь не заявляются.

## TC-2: zero timeout имеет разную семантику на двух границах

**P3 contract clarification**, не доказанное нарушение обещания unlimited execution.

- `crates/proteus-contracts/src/domain/tool.rs:295,318–320` допускает `with_timeout(0)`.
- `core/bound_tools/invocation.rs:26–29,71–76` при zero не запускает local tool timer.
- [`process_adapters/tool.rs:42–55`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/tool.rs#L42-L55) вычисляет `timeout_ms.unwrap_or(30_000).saturating_add(1_000)`: `Some(0)` превращается в protocol budget 1000 ms.
- Ненулевой explicit export override имеет приоритет (`process_adapters/config.rs:283–284`); кандидат относится к отсутствию override. Запрет zero в export config не запрещает zero в ToolSpec.
- `docs/guides/configuration.md:859–864` буквально описывает timeout+1000. Поэтому арифметика не обязательно противоречит документации. Вопрос в различной семантике одного sentinel value.
- Broker (`crates/proteus-module-protocol/src/v3/broker.rs:566–577`) требует положительный конечный timeout. Workflow/hook adapters при отключённом local deadline используют конечный default (`process_adapters/workflow.rs:49–53`, `hook.rs:20–24`). Нельзя механически отправить wire budget zero/unlimited.
- Stock producer с `Some(0)` не найден в проверенных source/config/examples. Это extension API edge case, не подтверждённая поломка штатного профиля.

### Решение и предлагаемый тест, НЕ ЗАПУЩЕН

Сначала выбрать контракт: zero отключает только local deadline при конечном process default, либо отдельно задаётся другой согласованный budget. Задокументировать одинаково для consumers; не объявлять unlimited semantics задним числом.

Сравнить один tool длительностью 2 s с timeout=0 через generic Tool и process export без override при внешнем бюджете 10 s. Controls: timeout=3000 и explicit export override. Проверить фактический outcome и cancellation settlement. Runtime measurements пока отсутствуют; тест не реализован.
