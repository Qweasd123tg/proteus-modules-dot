# Codex CLI и Claude Agent SDK: применимые механизмы для Proteus

Дата проверки: **28 октября 2026 года, UTC**. Метод: актуальная официальная документация и статическое чтение исходников. Оценки производительности ниже — гипотезы, не результаты измерений. Сборки и исполняемый код в рамках исследования не запускались.

## Краткий вывод

1. **Ближайшее небольшое улучшение — Rust-модуль ограничения суммарного размера выбранных tool-схем через существующий `hook/v6`.** В Proteus уже есть отбор по числу инструментов и оценка их размера; не хватает непосредственно применяемого агрегатного byte budget.
2. **Следующее алгоритмическое направление — предварительное уплотнение неизменяемого префикса истории с проверкой перед установкой результата.** Это требует явного владения фоновой задачей и не сводится к запуску потока внутри hook.
3. **Интеграция внешнего Codex/Claude harness возможна как отдельный адаптер**, но не является способом автоматически уменьшить память или ускорить Proteus.
4. Повторно создавать hooks, bounded queues, idle-history unloading, параллельный read-only tool dispatch и базовую compaction не требуется: значительная часть этого уже есть в закреплённых исходниках Proteus.

## Проверенные ревизии и границы сравнения

| Проект | Закреплённый источник |
|---|---|
| OpenAI Codex | [`1cc3cf8060c5f1dbd4e3a4d75e1a77b523e0c1ad`](https://github.com/openai/codex/commit/1cc3cf8060c5f1dbd4e3a4d75e1a77b523e0c1ad), актуальная вершина при проверке |
| Claude Agent SDK Python | [`2d485201617258867dd0f74b9e7307056f5938fe`](https://github.com/anthropics/claude-agent-sdk-python/commit/2d485201617258867dd0f74b9e7307056f5938fe), bundled CLI `2.1.312` |
| Proteus Core | [`125a9eb4088991513e9f61d899469be2076e266c`](https://github.com/Proteus-harness/Proteus-core/tree/125a9eb4088991513e9f61d899469be2076e266c) |
| Proteus Modules | [`5fa8978684a37e8083c64f4d6cf0289e72450c6a`](https://github.com/Proteus-harness/Proteus-modules/tree/5fa8978684a37e8083c64f4d6cf0289e72450c6a) |

Ревизии подтверждены ответами GitHub; это не утверждение о наличии криптографической подписи. Документация может меняться после даты проверки, поэтому механизмы из кода привязаны к SHA.

Codex публикует Rust harness и app-server. Claude Agent SDK — публичная Python/TypeScript-оболочка, запускающая Claude Code binary; её документация описывает доступные loop, tools, sessions и hooks. Это не основание приписывать закрытому binary конкретные внутренние структуры данных. Для программ на других языках Anthropic документирует CLI subprocess как интеграционную поверхность. [Официальный обзор Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview).

## 1. Tool discovery и ограничение контекста

### Подтверждённый механизм upstream

В текущей документации Claude tool search включён по умолчанию с оговорёнными исключениями совместимости. Режим `ENABLE_TOOL_SEARCH=auto` — отдельная настройка: откладывание активируется, когда откладываемые определения достигают 10% контекстного окна; `auto:N` меняет процент. Основные постоянно загруженные инструменты не входят в этот порог. Найденные определения остаются доступными до compaction соответствующих сообщений. Поиск добавляет round-trip, поэтому для небольшого каталога полная загрузка может быть быстрее. Это управление объёмом контекста, а не только количеством функций. [Официальная документация tool search](https://code.claude.com/docs/en/agent-sdk/tool-search).

Codex использует локальный индекс поиска и разделяет идентичность кандидата от материализации схемы:

- `ToolSearchEntry` содержит `Arc<ToolSpec>`;
- `tool_names()` перебирает identities без копирования полной схемы;
- `to_loadable_spec()` материализует выбранные результаты;
- cache сравнивает immutable источники через identity, а dynamic metadata — по значению;
- при поиске для code mode правила текущего шага применяются **до** ограничения числа результатов.

Источники: [представление схем](https://github.com/openai/codex/blob/1cc3cf8060c5f1dbd4e3a4d75e1a77b523e0c1ad/codex-rs/tools/src/tool_search.rs#L13-L94), [cache и поиск](https://github.com/openai/codex/blob/1cc3cf8060c5f1dbd4e3a4d75e1a77b523e0c1ad/codex-rs/core/src/tools/handlers/tool_search.rs). Имеющийся у Codex `tool_input_schema_max_bytes` относится к подготовке определений code mode; это не подтверждение наличия такого же агрегатного бюджета всего выбранного набора.

### Что уже есть в Proteus

`tool_selection.dynamic` ограничивает число обычных hot tools через `max_hot_tools`. При этом он сохраняет целиком зарегистрированную группу `proteus_agent_control`, provider-hosted инструменты и явно обязательные инструменты. Размер схем оценивается как сумма `serde_json::to_string(tool).len() / 4`, но эта оценка используется в metadata результата, а не как самостоятельный лимит выбора. Конфигурация содержит `max_hot_tools` и `always_include`, без byte budget. [Реализация](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/tool-selection-hook/src/lib.rs), [конфигурация](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/tool-selection-hook/src/config.rs).

### Предлагаемый дизайн: `tool-schema-budget`

Это новый небольшой алгоритм отбора, **а не копия внутренних алгоритмов Claude**:

1. Подключать после существующего ranking как обычный `BeforeToolSelection` handler.
2. Работать с уже допустимым набором; не возвращать скрытые предыдущим hook инструменты.
3. Сохранить обязательные группы, определённые контрактом/metadata, а не эвристикой по названию.
4. Подсчитать размер сериализованного представления набора. Явно определить, включаются ли JSON-обёртка и разделители.
5. Сохраняя порядок ranking, добавлять необязательные инструменты, пока они помещаются в бюджет.
6. Если обязательная группа превышает лимит, выдавать явный диагностический исход; не обрезать управляющий протокол и не заявлять соблюдение лимита.
7. Возвращать причины исключения, bytes до/после и отдельно приблизительные tokens.

Точка интеграции существует: `HookResponse::ToolSelection` проверяется относительно входных кандидатов и результата предыдущих hooks. Core не нужно заменять новым selector framework. [Контракт hooks](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/hook.rs).

**Ожидаемый эффект:** ограничение разрастания prompt payload при неодинаковых по размеру схемах; возможное сокращение сериализации и работы провайдера. **Ограничение:** bytes канонического `ToolSpec` не равны точным tokens и не обязательно равны окончательным bytes provider request после преобразования адаптером. Для жёсткого лимита провайдера нужен второй контроль в его render boundary. Дополнительный hook сам добавляет IPC; для малого каталога выгода может отсутствовать.

Дополнительную оптимизацию каталога — immutable schema cache и материализацию только выбранных схем — стоит рассматривать отдельно от семантики бюджета. `Arc` уменьшает копии внутри одного процесса, но не разделяет память между независимыми модулями. Protocol-level schema handles потребуют явного контракта invalidation и не должны скрыто добавляться в SDK v3.

## 2. Контекст, compaction и повторное использование

### Подтверждённый механизм upstream

Текущий Codex содержит speculative compaction: заранее захватывается snapshot, запускается session-owned задача, а подготовленный кандидат проверяется и применяется позднее. Повторные попытки различаются по данным контекста/модели; завершённый, но отброшенный запрос всё равно учитывается в расходе. Session shutdown отменяет остающуюся сетевую работу. Эта ветка gated и требует remote-compaction V2 capability. [Фоновая задача](https://github.com/openai/codex/blob/1cc3cf8060c5f1dbd4e3a4d75e1a77b523e0c1ad/codex-rs/core/src/session/async_compaction.rs).

Путь установки проверяет совместимость модели и compaction hash, заменяет только подтверждённый prefix и сохраняет live suffix. Неподходящий либо всё ещё превышающий бюджет результат может привести к foreground compaction. Это optimistic concurrency для истории, а не безусловная замена всего контекста готовой summary. [Установка результата](https://github.com/openai/codex/blob/1cc3cf8060c5f1dbd4e3a4d75e1a77b523e0c1ad/codex-rs/core/src/compact_remote_v2_installation.rs).

Claude документирует автоматическую compaction, событие `compact_boundary` и необходимость хранить устойчивые правила вне теряемой ранней истории. Prompt caching повторяемых префиксов — отдельный механизм; его нельзя отождествлять с сохранением decoded history в RAM процесса. [Документация agent loop](https://code.claude.com/docs/en/agent-sdk/agent-loop).

### Что уже есть в Proteus

- `codex-context-preparation` уже выполняет threshold-based compaction и формирует replacement history. [Compaction](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/codex-context-preparation/src/compaction.rs).
- Сохраняются пользовательские anchors и отдельно обрабатывается ephemeral context. [History](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/codex-context-preparation/src/history.rs).
- Idle session уже освобождает decoded history/model context и hibernate-ит writer, сохраняя identity/lease. Предложение «начать выгружать idle histories» дублировало бы реализацию. [Residency](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/runtime/residency.rs).

### Предлагаемый дизайн: подготовленный кандидат с проверяемым префиксом

Минимальная логическая запись кандидата:

```text
session_id
source_prefix_identity
model_identity + configuration_revision
summary + retained_anchors
accounted_usage
state: preparing | ready | rejected | adopted | canceled
```

Background-задача готовит только кандидат. Единственное изменение model-visible history происходит в host-owned boundary: проверить исходный prefix, сохранить появившийся suffix, повторно оценить бюджет, затем атомарно принять результат. При несовпадении — отбросить кандидат, не перезаписывая новые сообщения. Платёжный учёт сохраняется даже при отбрасывании.

**Нерешённая интеграционная граница:** нужно явное владение задачей после окончания invocation, ограничение числа кандидатов и допустимость поздних host callbacks. Запуск неучтённого потока в `TurnSettled` не является корректной реализацией. При отсутствии такого lifecycle в текущем контракте это расширение Core, а не готовый автономный модуль.

**Ожидаемый эффект:** убрать ожидание summarization с критического пути следующего шага. **Риски:** дополнительная память snapshot, лишние запросы, stale candidates, потеря полезного контекста, изменение prompt-cache prefix. Портируемый вариант может использовать обычную модель summary, но тогда это собственный алгоритм Proteus, а не обещание совместимости с Codex remote V2.

## 3. Исполнение tools, cancellation и backpressure

### Подтверждённые различия

В Codex outbound transport bounded: для соединений, которые можно отключить, заполненная очередь приводит к disconnect медленного клиента; для другого пути отправка ожидает освобождения очереди. Это конкретная политика перегрузки, а не универсальная гарантия неблокирующей доставки. [Transport](https://github.com/openai/codex/blob/1cc3cf8060c5f1dbd4e3a4d75e1a77b523e0c1ad/codex-rs/app-server/src/transport.rs#L142-L181).

Claude Python SDK маршрутизирует bidirectional control messages, отслеживает pending callbacks и обрабатывает `control_cancel_request`. Обычные сообщения помещаются в очередь ёмкостью 100 через ожидаемый `send`. Поэтому из этого кода нельзя заключать, что заполненная application queue никогда не задерживает последующие control frames. Это статическое наблюдение, не воспроизведённая ошибка. [Query](https://github.com/anthropics/claude-agent-sdk-python/blob/2d485201617258867dd0f74b9e7307056f5938fe/src/claude_agent_sdk/_internal/query.py#L388-L506).

Транспорт Claude ограничивает отдельные NDJSON-сообщения, сериализует записи и выполняет ограниченный по времени shutdown с ожиданием, terminate и kill. В комментариях исходника отдельно отмечены ограничения shield при внешней asyncio cancellation. Это полезный образец явного описания гарантий, но не основание считать cleanup безусловно совершенным. [Subprocess transport](https://github.com/anthropics/claude-agent-sdk-python/blob/2d485201617258867dd0f74b9e7307056f5938fe/src/claude_agent_sdk/_internal/transport/subprocess_cli.py).

### Proteus уже располагает необходимыми примитивами

| Примитив | Подтверждённая реализация |
|---|---|
| Раздельные control/data writer lanes | Bounded frames и bytes, резерв для control, withdrawal frame до начала записи. [Writer](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-process-host/src/writer.rs) |
| Ограничение чтения | Aggregate budget количества кадров и bytes плюс отдельные framing limits. [Receive](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-process-host/src/receive.rs) |
| Terminal независимо от notifications | Раздельные каналы; потеря result receiver считается cancellation. [Invocation](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-module-protocol/src/v3/invocation.rs) |
| Параллельные безопасные tools | `Gate` допускает concurrent readers и эксклюзивный writer, сохраняет порядок admission и собирает результаты в исходном порядке. [In-flight tools](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/workflow/coding-workflow/src/codex_stream/in_flight.rs) |
| UI/event delivery | Bounded broadcast и latest snapshot через watch. [Events](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/app_server/events.rs) |

**Практический вывод:** не заменять SDK v3 более примитивной общей очередью по образцу внешнего SDK. Для новых adapters переиспользовать существующие terminal/control lanes и явно сопоставлять transport overload, invocation timeout и cancellation, а не сводить их к одному текстовому error.

## 4. Session lifecycle и адаптеры внешних harness

### Подтверждённый механизм

Codex app-server использует двунаправленный JSON-RPC-подобный протокол с thread/turn/item identifiers, initialization handshake, `turn/steer` с ожидаемым turn ID и `turn/interrupt`. Pending approvals разрешаются отдельным request/response round-trip; `serverRequest/resolved` сообщает об ответе либо очистке. Чтение stored thread отделено от его загрузки для исполнения. Для прототипа предпочтителен local stdio; WebSocket документирован как experimental/unsupported. [Официальный app-server protocol](https://learn.chatgpt.com/docs/app-server).

В Claude важен другой lifecycle-предел: `result` заканчивает turn, но не обязательно весь run. Background agent может вызвать следующий turn, которому ещё нужны callbacks. Текущий Python SDK удерживает stdin для таких потребностей до idle/разрешённого завершения run и документирует ограничения старых CLI без session-state событий. [Реализация](https://github.com/anthropics/claude-agent-sdk-python/blob/2d485201617258867dd0f74b9e7307056f5938fe/src/claude_agent_sdk/_internal/query.py#L1038-L1091). Persistent streaming input поддерживает новые сообщения и interruption. [Документация](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode).

### Интеграция с Proteus

Текущий process-agent backend запускает `proteus ... server stdio` и читает типизированный протокол Proteus. Простая подмена executable на `codex` или `claude` не делает его совместимым. [Child process](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/agent_control/process/child.rs).

Отдельный Rust adapter должен владеть:

- mapping локальных и upstream session/turn/request IDs;
- состояниями running, waiting-for-input, canceling, settled и disconnected;
- корреляцией approval requests и очисткой их при interrupt/disconnect;
- сериализацией управляющих сообщений без ожидания UI-render;
- pin версии wire schema и явной обработкой неизвестных событий;
- сохранением upstream resume handle без выдуманного перевода закрытого контекста;
- границей между завершением ответа, завершением run и остановкой процесса.

Это отдельная интеграция, не обязательная замена собственного workflow. Persistent subprocess может уменьшить повторный startup, но увеличивает idle RSS и добавляет ещё один harness. Утверждать ускорение без конкретного рабочего сценария нельзя.

## 5. Permissions и extensible hooks

### Подтверждённые границы

В актуальном Claude permission flow hooks идут раньше deny/ask rules, однако `allow` из hook не отменяет эти правила. Callback `canUseTool` — только часть общего принятия решения, не универсальный обход остальных ограничений. [Permissions](https://code.claude.com/docs/en/agent-sdk/permissions).

Proteus уже имеет thread/execution-scoped approval cache с canonical args и исключениями для инструментов, которым нельзя переиспользовать grant. [Approval cache](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/approval/cache.rs). Перенос внешнего решения должен сохранять scope, аргументы и контекст запроса; неизвестная семантика не должна превращаться в более широкое разрешение.

**Важная интеграционная ловушка Codex:** `thread/shellCommand` документирован как выполнение вне sandbox, без наследования thread sandbox policy. Этот endpoint нельзя использовать как реализацию обычного model-visible shell tool Proteus. Он предназначен для явно инициированных пользователем команд. [Описание endpoint](https://learn.chatgpt.com/docs/app-server#run-a-thread-shell-command).

### Hooks: расширять совместимость, а не создавать framework повторно

Proteus `hook/v6` уже покрывает tool selection, context preparation, model request, before/after tool, stop и settled turn. Ответы применяются типизированно, сохраняют identity сообщений и перепроверяются. [Контракт](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/hook.rs).

Кроме того, уже существует `claude-command-hooks` в режиме `strict_subset`: `PreToolUse`, `Stop`, argument mapping, лимиты, cancellation; `allow` не выдаёт разрешение в обход host. Нет общей загрузки произвольных Claude plugins и нет заявленной полной совместимости. [Адаптер](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/claude-command-hooks/README.md).

**Небольшое возможное расширение:** явно описанный observational subset `PostToolUse`/failure через существующий `AfterTool`, с точным отображением доступных полей и отказом на непредставимых ответах. Это прежде всего функциональная совместимость, не доказанная оптимизация.

Асинхронный hook, уже отпустивший операцию, не должен затем менять разрешение или результат задним числом. Claude документирует async output только для side effects, а не для блокирования, изменения или добавления контекста в уже продолжающуюся операцию. Эту границу следует сохранить. [Hooks](https://code.claude.com/docs/en/agent-sdk/hooks).

## Очерёдность внедрения

| Приоритет | Изменение | Где | Ожидаемая польза | Главное ограничение |
|---|---|---|---|---|
| 1 | Агрегатный schema-byte budget | Новый небольшой Rust `hook/v6` либо опция существующего selector | Предсказуемый размер hot catalog | Не считать bytes точными tokens; не ломать обязательные группы |
| 2 | Immutable catalog / selected-only materialization | Внутри selector/catalog | Меньше копий и повторной подготовки | Не обещает shared memory между процессами |
| 3 | Prefix-validated prepared compaction | Context preparation + явный host lifecycle | Меньше foreground ожидания summary | Требует безопасного владения фоновой задачей и учёта stale результатов |
| По потребности | Внешний Codex/Claude harness adapter | Отдельный процессный адаптер | Доступ к существующим внешним агентам | Дополнительный runtime, несовпадающие wire и permission semantics |
| По потребности | Расширение Claude hook subset | Существующий compatibility adapter | Повторное использование большего числа hooks | Не полная совместимость; trusted command code остаётся исполняемым кодом |

Ни один из этих пунктов сам по себе не доказывает ускорение end-to-end: существенную часть времени обычно занимает модель, сеть и реальные tools. Здесь установлены конкретные алгоритмические возможности и точки интеграции; измеренные проценты экономии не заявляются.
