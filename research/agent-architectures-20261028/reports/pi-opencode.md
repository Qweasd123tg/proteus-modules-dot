# Pi и OpenCode как источники runtime улучшений Proteus

Дата проверки: 28 октября 2026 года. Цель — выбрать переносимые механизмы исполнения и узкие Rust-компоненты, не дублирующие действующую архитектуру Proteus.

**Главный вывод:** первым небольшим расширением стоит делать бюджет сериализованных tool-схем поверх существующего selector. Из более крупных runtime-изменений обоснованы координация файловых изменений по ресурсам на стороне host и предварительная compaction с отложенным применением. Общие hooks, cancellation, ограниченные очереди, session persistence и усечение вывода заново создавать не нужно.

Утверждения ниже разделены на прочитанные механизмы upstream, состояние закреплённой версии Proteus и предлагаемый дизайн. Ускорение, экономия токенов и RSS не измерялись.

## Проверенные версии

| Проект | Прочитанная ревизия | Последний release на момент проверки |
| --- | --- | --- |
| Pi | [`earendil-works/pi` — `ad702637fdf6fbd3f965c5dba0b14bae100b74eb`](https://github.com/earendil-works/pi/commit/ad702637fdf6fbd3f965c5dba0b14bae100b74eb), `main`, 28 октября 2026 | [`v1.4.0`](https://github.com/earendil-works/pi/releases/tag/v1.4.0), 21 октября 2026 |
| OpenCode | [`anomalyco/opencode` — `b6c43a524265496086fc0fdd83180bfa47d4d22e`](https://github.com/anomalyco/opencode/commit/b6c43a524265496086fc0fdd83180bfa47d4d22e), `dev`, 28 октября 2026 | [`v1.19.5`](https://github.com/anomalyco/opencode/releases/tag/v1.19.5), 28 октября 2026 |
| Proteus Core | [`125a9eb4088991513e9f61d899469be2076e266c`](https://github.com/Proteus-harness/Proteus-core/tree/125a9eb4088991513e9f61d899469be2076e266c) | База сравнения, не проверка последнего release |
| Proteus Modules | [`5fa8978684a37e8083c64f4d6cf0289e72450c6a`](https://github.com/Proteus-harness/Proteus-modules/tree/5fa8978684a37e8083c64f4d6cf0289e72450c6a) | База сравнения, не проверка последнего release |

Рассмотрены указанные HEAD, а не предполагаемое содержимое release-коммитов. Нынешний Pi проверен по `earendil-works/pi`; одноимённый старый Go-проект OpenCode не смешивается с `anomalyco/opencode`. Существование commit SHA не означает проверки криптографической подписи.

## Архитектура сессий и расширений

### Pi

Pi хранит JSONL-сессию как дерево записей с `id` и `parentId`. Контекст строится по текущей ветке; compaction ссылается на сохранённую границу истории. Начальная системная запись содержит prompt sections и декларации инструментов, последующие системные записи могут добавлять и удалять tools и изменять отдельные prompt sections. Это делает tool loadout частью воспроизводимого транскрипта. [Формат сессии](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/docs/session-format.md), [SessionManager](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/src/core/session-manager.ts).

Agent loop работает с `AgentMessage` и преобразует сообщения в provider representation на границе LLM-вызова. Поддержаны отдельные steering и follow-up queues. После длительной подготовки следующего turn, например compaction, loop повторно проверяет steering, если предыдущая проверка ничего не вернула. Tool lifecycle включает подготовку аргументов, schema validation, before hook, выполнение и after hook. Вложенные tool calls могут использовать тот же `runToolCall`, не обходя hooks. [Agent loop](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/agent/src/agent-loop.ts#L172-L235), [tool lifecycle](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/agent/src/agent-loop.ts#L718-L860).

Extensions — TypeScript API внутри runtime, а не стабильный бинарный ABI для Rust. При смене сессии `AgentSessionRuntime` сначала abort/settle текущую работу, отправляет shutdown event, затем инвалидирует старый runtime. Это полезный порядок teardown, но не основание заменять процессную изоляцию Proteus. [Runtime replacement](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/src/core/agent-session-runtime.ts#L163-L178), [extensions API](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/docs/extensions.md).

### OpenCode

В прочитанной версии OpenCode durable events записываются с последовательностью aggregate и проецируются в представление сообщений. Durable follower получает сигнал о новых данных и перечитывает события по cursor из хранилища. Live subscriptions и durable log — разные механизмы, с разными свойствами памяти и восстановления. [Bus](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/bus.ts), [message projection](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/session/message-updater.ts).

Plugin API предоставляет Effect/Promise-интерфейсы и scoped registrations. В hook dispatcher обработчики выполняются последовательно; регистрация снимается scope finalizer. Supervisor при неудачной загрузке новой ревизии может сохранить предыдущую работающую generation вместо потери всего набора. Это lifecycle-паттерны, не бинарный extension ABI. [Plugin interface](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/plugin/src/effect/plugin.ts), [hook dispatcher](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/plugin/hooks.ts), [supervisor](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/plugin/supervisor.ts).

## Приоритет 1 Бюджет tool схем без нового discovery framework

**Механизм Pi.** Встроенный `tool_search` использует BM25 по metadata, descriptions и schema property names. Явное совпадение имени получает приоритет; результат ограничивается числом инструментов. `searchAndLoad` добавляет найденные инструменты к активному набору. В рассмотренном коде нет агрегатного ограничения сериализованных schema bytes. [Ранжирование и активация](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/src/extensions/tool-search/tool.ts#L149-L232).

У Proteus уже есть `tool-selection-hook`, поэтому отдельный общий tool-search framework был бы неверным первым шагом. Узкое расширение — учитывать бюджет фактически сериализуемого выбранного набора, сохраняя existing selection semantics. [Существующий selector](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/tool-selection-hook/src/lib.rs).

**Предлагаемый Rust-дизайн:** детерминированный admission pass поверх упорядоченного списка выбранных tools. Он сохраняет обязательные управляющие инструменты и связанные provider-hosted группы, не меняет схемы, visibility или permissions. При превышении бюджета обязательной группой возвращает явную диагностику, а не скрыто удаляет её. Точные UTF-8/JSON bytes и приблизительные tokens должны быть разными полями. Provider-neutral bytes не являются точным токеновым лимитом конкретной модели.

Важен не только размер, но и стабильность набора. Pi добавляет prompt/tool deltas в транскрипт; provider, который не умеет представить такой переход, получает полный checkpoint, потенциально теряя cache reuse. Следовательно, полезны устойчивый порядок и отсутствие бессмысленного изменения выбранного набора между соседними запросами. [Dynamic tools](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/docs/extensions.md#dynamic-tools).

**Ожидаемый эффект:** меньше prompt payload и сериализации при больших каталогах. Это гипотеза, не измеренное ускорение. Byte-budget — собственное дополнение Proteus, а не заявленный механизм Pi.

## Приоритет 2 Координация файловых изменений на стороне host

### Проверенное различие

Pi `withFileMutationQueue` строит ключ по `realpath`, сериализует операции одного файла и не блокирует операции независимых файлов. Для отсутствующего пути используется resolved path. `write` удерживает очередь до окончания текущего filesystem await даже после abort: преждевременное освобождение позволило бы второй записи пересечься с первой. [Очередь](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/src/core/tools/file-mutation-queue.ts), [write cancellation](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/src/core/tools/write.ts#L66-L87).

В Modules `edit` и `write` явно имеют `supports_parallel_tool_calls:false`. Рассмотренный Core `ToolSpec` содержит scheduling boolean, но не типизированный per-call resource footprint. `CodexToolBatch::permits_parallel` требует разрешения каждого инструмента в batch. [Edit](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/tool/file-tools/src/edit.rs), [write](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/tool/file-tools/src/write.rs), [ToolSpec](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/domain/tool.rs#L283-L301), [batch scheduling](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/workflow/coding-workflow/src/codex_tools.rs#L65-L72).

Это обосновывает host-level оптимизацию, но **не разрешает просто переключить boolean** или добавить mutex только внутри file-tools subprocess.

### Минимальный недостающий контракт

Предлагаемый, ещё не реализованный контракт:

```rust
enum MutationFootprint {
    Paths(Vec<ResourceKey>),
    WorkspaceExclusive,
}

struct MutationLease {
    invocation: InvocationId,
    resources: Vec<ResourceKey>,
    // Владение host/coordinator, а не lifetime вызывающего future.
}
```

1. Footprint получается по окончательным аргументам после `before_tool` transformations; источник декларации проверяется host, неизвестный или неполный footprint не считается безопасным.
2. Lease привязывается к invocation, workspace identity и configuration epoch. Shell, неизвестные mutations и неподдерживаемые paths получают `WorkspaceExclusive`.
3. Набор путей захватывается в детерминированном порядке. Rename учитывает source и destination; multi-file patch — весь набор до первой записи.
4. Ожидание admission отменяемо. Timeout semantics очереди задаются явно, а не случайно наследуются от времени исполнения.
5. Nested calls требуют явных правил владения и расширения footprint: нельзя допустить самоблокировку или скрыто выдать больший lease.

Первый seam интеграции — `BoundTools::invoke_allowed`, после validation, before hooks и policy/approval, но до фактического вызова tool. Это сохраняет единую execution boundary и для вложенных обращений. [Общий путь](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/bound_tools.rs#L294-L396), [invoke_allowed](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/bound_tools/invocation.rs).

### Cancellation не равно окончанию записи

В текущем `invoke_allowed` timeout/cancel даёт invocation до **500 ms** на settlement, после чего формируется результат. Обычный RAII guard, привязанный к этому future, может освободить путь до физического окончания записи worker. Поэтому lease обязан удерживаться до подтверждённого side-effect settlement либо подтверждённой остановки исполняющего процесса. Cancel ACK или возвращённый `ToolResult` сами по себе недостаточны. При неопределённом исходе нужен консервативный барьер/карантин workspace; нельзя автоматически допускать следующую запись. [Cancellation settlement](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/bound_tools/invocation.rs).

Удержание lease не означает rollback уже сделанных изменений. Механизм не должен обещать атомарность multi-file операции, если её не обеспечивает сам инструмент.

### Межпроцессная граница и файловая идентичность

Mutex-карта одного компонента не защищает другие subprocess, subagents или второй Core process. Координатор должен принадлежать общему workspace owner и обслуживать участников через IPC либо использовать согласованные OS locks. Advisory locks защищают только участников того же протокола; семантика network filesystem и платформ различается. Сторонний редактор не становится участником автоматически.

`realpath` — полезный ключ, но не полное решение: остаются hardlinks, case sensitivity, создание отсутствующего пути, изменение symlink/parent directory между проверкой и записью. Нужны повторная проверка идентичности при admission и безопасная деградация на workspace-exclusive режим. Этот scheduler не расширяет filesystem permissions и не заменяет sandbox.

**Ожидаемый эффект:** параллельные изменения независимых файлов при сохранении порядка конфликтующих. Польза зависит от реальных batch и затрат subprocess; измеренного результата пока нет.

## Приоритет 3 Предварительная compaction с отложенным применением

### Что реализовано в OpenCode

При приближении к порогу OpenCode может запустить summary вне критического пути. Готовая summary удерживается и не заменяет историю до фактической необходимости compaction: преждевременная замена изменила бы prefix и нарушила cache reuse последующих запросов. В прочитанной конфигурации **`precompute:false` по умолчанию**. [Настройка и механизм](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/session/compaction.ts#L261-L418).

Проверка `heldIndex` сравнивает:

- `firstID` с первым сообщением текущего context;
- сохранённый `initial` с текущими instructions;
- `providerID`, model `id` и `variant`;
- наличие границы `keepID` в текущем context.

Отдельно проверяются длина сохранённого live tail, тип compaction и причина запуска. Это **не криптографический hash содержимого всего prefix**. При непригодном или неуспешном кандидате используется обычный foreground путь. [Точные поля проверки](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/session/compaction.ts#L949-L966), [приём результата](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/session/compaction.ts#L391-L418).

### Что уже есть в Proteus и что добавлять

`codex-context-preparation` уже реализует threshold → synchronous model summary → replacement, сохраняет ephemeral context и выбранные user messages. Новый общий compaction module не нужен. [Реализация](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/codex-context-preparation/src/compaction.rs).

Предлагается session/workflow-owned candidate:

```text
session + prefix revision/digest + config/policy epoch
model identity + boundary + summary + usage
```

Prefix digest и epoch здесь — усиление предлагаемого Proteus-дизайна, не приписываемая OpenCode проверка. Background job возвращает кандидата, но не переписывает историю. Host выполняет compare-and-replace и сохраняет suffix, появившийся после snapshot. При несовпадении контекста, отмене или недостаточном сжатии используется существующий foreground путь.

Это не маленький hook без изменений lifecycle. Сначала нужен подтверждённый контракт владения background task и model callbacks после завершения исходной invocation. Нельзя обходить invocation-bound authority скрытым потоком, который продолжает host calls после её окончания.

**Цена и ограничения:** дополнительный model request, стоимость отброшенных результатов, память snapshot, конкуренция за provider quota. Приоритет — opt-in с ограниченным числом кандидатов и полным usage accounting, не безусловное включение для всех сессий. Уменьшение пользовательской задержки пока остаётся гипотезой.

## Scheduling и lifecycle уроки

### Окончание turn и освобождение ресурса должны различаться

OpenCode `SessionRunCoordinator` хранит один execution на key. Coalesced `pendingWake` закрывает окно между последней проверкой очереди и переходом в idle. `interrupt` подтверждает принятие отмены, но не завершение cleanup; `awaitIdle` ждёт settlement. Wake, пришедший во время cleanup, может породить successor execution. Это пригодный reference state machine, **не обнаруженная ошибка текущего Proteus**. [Run coordinator](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/session/run-coordinator.ts).

Pi codemode также различает логический результат и освобождение worker. Admission ожидает свободный slot в FIFO-порядке, учитывает ожидание в deadline и поддерживает abort. По умолчанию доступны два worker, QuickJS VM имеет heap limit 256 MiB. Slot возвращается при фактическом worker exit, даже если aborted result уже отдан вызывающему. [Admission](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/src/extensions/codemode/execute.ts#L49-L110), [worker termination](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/codemode/src/runtime/host.ts).

Для Proteus это правило владения scarce resources: не освобождать permit только потому, что запрос получил canceled outcome. Оно особенно важно для mutation leases и процессов, которые ещё завершают side effects.

## Память и backpressure без ложных обещаний

- **Pi EventStream не ограничивает очередь:** использует FIFO из двух массивов. В tool execution partial-update promises накапливаются до завершения tool. Эти реализации нельзя приводить как доказательство bounded backpressure. [EventStream](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/ai/src/utils/event-stream.ts), [partial updates](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/agent/src/agent-loop.ts#L831-L860).
- **Pi output accumulator ограничивает display tail и сохраняет полный вывод в spill file**, но не ожидает drain после `write(data)`. Это не жёсткая верхняя граница RAM всей I/O цепочки при медленном диске. [Accumulator](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/src/core/tools/output-accumulator.ts).
- **OpenCode durable wake capacity равна 1**, потому что уведомление лишь сообщает о новых сохранённых событиях; они читаются по sequence из DB. Но live и typed PubSub в том же bus — unbounded. Переносить надо конкретное свойство durable reader, а не объявлять весь event bus ограниченным. [Subscriptions](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/bus.ts#L749-L891).
- **OpenCode объединяет streaming deltas за 100 ms**, сохраняет fragment identity/ordinal и выполняет flush на границах. Это снижает число событий, но full response всё ещё накапливается в fragments и соединяется при завершении; bounded total memory из этого не следует. [Publisher](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/session/runner/publish-llm-event.ts#L98-L228).
- **OpenCode media blobs** вынесены из message rows и гидратируются по необходимости; записи без refs возвращаются без переписывания. Это полезный принцип lazy materialization, но не утверждение о zero-copy всей цепочки: base64 representation всё равно создаётся на границе hydration. [Blob handling](https://github.com/anomalyco/opencode/blob/b6c43a524265496086fc0fdd83180bfa47d4d22e/packages/core/src/session/blob.ts#L77-L148).

В Proteus уже существуют bounded head+tail для shell output и отдельный research artifact store, исключённый из production workspace. Новый generic truncator дублировал бы имеющуюся работу. Если развивать artifacts, нужно отдельно интегрировать streaming spill до потери середины вывода, а не сохранять уже усечённый результат. [Shell output](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/tool/shell-tool/src/unified_exec/output.rs), [research artifact store](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/research/tool-output-artifacts/src/lib.rs).

Также в Core authoritative session view обновляется без промежуточной broadcast-очереди, способной потерять deltas. Поэтому предложение нового event layer требует сначала показать конкретный недостающий участок, а не заменять существующий механизм целиком. [RuntimeEventSink](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/app_server/events/session.rs#L193-L220).

## Что не ставить в ближайший план

Pi содержит экономически управляемый cache warmer: учитывает TTL, ожидаемую выгоду и replay compatibility; прекращает warming по safety limits. Однако его вероятность idle continuation и стоимостные пороги — upstream-эвристики, а не измерения Proteus. Дополнительные платные запросы и provider-specific cache semantics делают прямой перенос менее обоснованным, чем уменьшение tool payload и сохранение стабильного prefix. [Cache warmer](https://github.com/earendil-works/pi/blob/ad702637fdf6fbd3f965c5dba0b14bae100b74eb/packages/coding-agent/src/core/cache-warmer.ts).

Не предлагаются новая extension ABI вместо v3 process protocol, общий scheduler вместо существующего execution layer, повторная реализация output truncation или включение параллельных mutations без ресурсо-ориентированного контракта.

## Порядок интеграции

| Очерёдность | Изменение | Граница реализации | Условие безопасного продолжения |
| --- | --- | --- | --- |
| 1 | Schema byte budget | Существующий tool-selection hook | Детерминированный порядок, сохранение обязательных tools и явная диагностика overflow |
| 2 | Mutation footprint и leases | Core host и существующие file tools | Общий cross-process owner, физическое settlement, безопасная идентичность paths |
| 3 | Speculative compaction | Существующий compactor плюс session/workflow-owned job | Подтверждённый background lifecycle и host-only compare-and-replace |
| Позже | Stream coalescing или lazy blobs | Только найденный горячий участок | Доказанная избыточная сериализация/материализация без дублирования текущего event layer |

Mutation coordination и speculative compaction являются проектами runtime, а не обещанием готового plug-in без изменения контрактов. Небольшой byte-budget hook позволяет начать с ограниченного, понятного расширения уже выбранного механизма.

## Статус проверки

Выполнено чтение закреплённых исходников и официальных upstream releases. Код upstream и пользователя не запускался; сборки, тесты, CI, публикация и remote mutations не выполнялись. Permission blockers при чтении отсутствовали. Открытые технические вопросы — межпроцессное владение mutation leases и подтверждение side-effect settlement, а также session-owned background lifetime для compaction. Заявлений о достигнутом ускорении нет.
