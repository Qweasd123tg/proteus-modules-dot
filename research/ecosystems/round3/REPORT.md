# OpenHands SDK: действия, окружение и восстановление

Исходники: **OpenHands/software-agent-sdk `ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50`**, Git tree `5e0d3f571c7be2bfd8ecc8b3fce08e23626065b6`. Срез 25 октября 2026, источник закреплён, не плавающий main. Текущий локальный Core: `1fc3ef223d10322815dd9290a50d045bc95402bb`; SDK опубликованных примеров: `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`.

## Итог

Наиболее полезен не очередной agent loop, а разделение четырёх вещей: **запрос действия, фактический эффект, представление результата для модели и срок жизни окружения**. OpenHands содержит отдельные action/observation events, восстановление model-view, lease generation для записей, admission permit для цепочки runs и самостоятельный workspace/browser lifecycle. Эти части не дают общей exactly-once транзакции.

Proteus уже имеет общий BoundTools/approval path, canonical identity, raw effect recording, cooperative cancellation, versioned ConversationView и explicit process launch policy. Их не следует заменять импортом foreign runtime или ещё одним универсальным DTO. Реальный недостающий producer для исследовательского сценария — проверка точной цитаты в разрешённом локальном source artifact. Она не требует браузера, network или нового Core slot.

31 targeted source file, **820440 bytes**. Все pinned tree / connector / local Git blob hashes совпали. Прочитаны указанные частичные диапазоны; это не аудит всего репозитория. Ни один upstream script/test/tool/model/browser не исполнялся. Runtime outcomes и performance не измерялись. Частные неподтверждённые вопросы находятся отдельно и не предназначены для публикации.

## Жизненный цикл в прочитанном срезе

1. Conversation создаёт/возобновляет base state и event log. Context View выводится из активной ветки с condensation и structural repair.
2. Agent получает действия, выделяет parsed arguments, связывает event ID/tool-call ID/batch ID. Confirmation может остановить run; следующий run выполняет pending actions.
3. Batch executor применяет hook blocking, resource locks и per-agent worker bound. Результаты публикуются в исходном action order, а не completion order.
4. Interrupt сигнализирует token/task; conversation может стать PAUSED, пока отдельный worker/resource ещё завершается. Server RunSlot не отдаёт admission permit только из-за cancellation waiter.
5. Persisted RUNNING после restart становится ERROR с synthetic observation. Это repair transcript, не rollback filesystem/browser.
6. Conversation close, browser cleanup, workspace pause и container removal — отдельные операции разных owners. Успех одного слоя не означает подтверждённый успех остальных.

## Наблюдения и перенос в Proteus

### ECO3-01. Action, observation и model-view — разные объекты

**В исходниках.** ActionEvent отдельно хранит event.id, tool_call_id, llm_response_id, исходный tool_call и parsed action; ObservationEvent связывается с action_id. Parsed action может отличаться от исходных arguments (например, вынесенная risk annotation).

**Для Proteus.** Для аудита использовать отдельные correlation IDs и точные bytes нужного слоя, а не строковый transcript. В Proteus уже есть canonical ToolCall/ToolResult и owner attribution; новый универсальный foreign-event DTO не нужен.

**Граница вывода.** Внешняя risk annotation и тип события не доказывают авторизацию либо реальный effect.

Источники: [llm_convertible/action.py L39-L85](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/event/llm_convertible/action.py#L39-L85), [llm_convertible/observation.py L17-L72](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/event/llm_convertible/observation.py#L17-L72); [Core domain/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/domain/tool.rs#L86-L135).

### ECO3-02. Повтор run — implicit approval в SDK, не универсальная host admission

**В исходниках.** Agent._step/_astep выполняют unmatched actions до новой model sampling. run() очищает WAITING_FOR_CONFIRMATION; rejection добавляет отдельное observation. Публичный LocalConversation.execute_tool прямо обходит confirmation/security analysis.

**Для Proteus.** При адаптации не превращать generic resume в разрешение эффекта. Proteus BoundTools уже проводит nested/tool execution через validation, policy и approval; сохранить этот единственный путь.

**Граница вывода.** Это задокументированная граница library API, не подтвержденная уязвимость server API; server authorization целиком не исследован.

Источники: [agent/agent.py L703-L719](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/agent/agent.py#L703-L719), [agent/agent.py L1127-L1198](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/agent/agent.py#L1127-L1198), [impl/local_conversation.py L1959-L1969](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L1959-L1969), [impl/local_conversation.py L2706-L2744](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L2706-L2744), [impl/local_conversation.py L3183-L3224](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L3183-L3224); [Core core/bound_tools.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools.rs#L294-L432).

### ECO3-03. Полный event log, активная ветка и подготовленный context не взаимозаменяемы

**В исходниках.** EventLog хранит parent_id дерево; active_branch исключает abandoned branches. View применяет condensation, исключает non-LLM events и удаляет незавершённые pairs/batches либо поздние duplicate observations при enforcement.

**Для Proteus.** Research citation должен указывать слой и immutable artifact hash. Не использовать очищенный model-view как доказательство отсутствия действия. Core ConversationView уже явно ограничен current canonical history после compaction.

**Граница вывода.** Инкрементальная обработка хвоста описана кодом; latency/speedup не измерялись.

Источники: [conversation/event_store.py L95-L130](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/event_store.py#L95-L130), [conversation/state.py L295-L405](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/state.py#L295-L405), [view/view.py L74-L160](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/context/view/view.py#L74-L160), [properties/observation_uniqueness.py L18-L52](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/context/view/properties/observation_uniqueness.py#L18-L52), [properties/batch_atomicity.py L10-L47](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/context/view/properties/batch_atomicity.py#L10-L47); [Core conversation/view.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/contracts/conversation/view.rs#L1-L55).

### ECO3-04. Durability состоит из нескольких отдельных операций

**В исходниках.** EventLog append держит file lock, пишет событие и затем обновляет length marker; marker удаляется прежде нового, чтобы interrupted update давал fallback count. Base state сохраняется отдельно. atomic_write_text делает temp+flush+fsync(file)+replace.

**Для Proteus.** Разделять durable event, base projection и cache; recovery должен учитывать lag HEAD. Не объявлять file fsync общей multi-file transaction или гарантией power-loss durability каталога.

**Граница вывода.** LocalFileStore cache требует exclusive file ownership; NFS caveat явно указан EventLog. Полная crash matrix не исполнялась.

Источники: [conversation/event_store.py L188-L271](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/event_store.py#L188-L271), [conversation/state.py L315-L337](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/state.py#L315-L337), [conversation/state.py L430-L451](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/state.py#L430-L451), [utils/files.py L21-L50](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/utils/files.py#L21-L50); [Core runtime/conversation.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/runtime/conversation.rs#L33-L47).

### ECO3-05. Lease generation ограждает записи, а не внешние эффекты

**В исходниках.** ConversationLease.claim увеличивает generation при takeover; guarded_write проверяет owner+generation под lock. EventService устанавливает этот guard на ConversationState/EventLog после загрузки и обновляет lease. TTL=0 явно отключает leasing.

**Для Proteus.** Для environment driver различать writer ownership и реальную остановку browser/command operation. Любое CAS-предложение Proteus должно назвать настоящий backend, owner и transaction boundary; host.read_file/write_file сами не создают CAS.

**Граница вывода.** Не заявляется global fencing tool effects; lease-файлы и state writes не являются browser transaction.

Источники: [agent_server/conversation_lease.py L122-L164](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/conversation_lease.py#L122-L164), [agent_server/conversation_lease.py L187-L232](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/conversation_lease.py#L187-L232), [agent_server/event_service.py L495-L529](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/event_service.py#L495-L529), [agent_server/event_service.py L1237-L1252](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/event_service.py#L1237-L1252), [agent_server/event_service.py L1388-L1407](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/event_service.py#L1388-L1407); [Core bound_tools/invocation.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/invocation.rs#L30-L62).

### ECO3-06. Cancel, PAUSED и завершение worker различны

**В исходниках.** interrupt сначала отменяет thread-safe token, затем async task; sync run получает pause. _arun ловит CancelledError, добавляет synthetic error для orphan tool calls и становится PAUSED. ToolExecutor.interrupt по умолчанию no-op; работа thread может пережить async waiter.

**Для Proteus.** Сохранять canceled/unknown outcome, не обещать rollback. Core уже даёт child cancellation, 500ms settlement grace и metadata canceled/timed_out; модуль проверяет host cancellation, но не выдаёт себя за OS supervisor.

**Граница вывода.** Synthetic tool error обеспечивает формат conversation, не подтверждает отсутствие внешнего эффекта.

Источники: [conversation/cancellation.py L1-L43](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/cancellation.py#L1-L43), [impl/local_conversation.py L2588-L2623](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L2588-L2623), [impl/local_conversation.py L2666-L2672](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L2666-L2672), [impl/local_conversation.py L2801-L2834](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L2801-L2834), [agent/parallel_executor.py L193-L253](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/agent/parallel_executor.py#L193-L253), [tool/tool.py L308-L327](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/tool/tool.py#L308-L327); [Core contracts/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/contracts/tool.rs#L54-L114), [Core bound_tools/invocation.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/invocation.rs#L79-L122).

### ECO3-07. Capacity permit принадлежит цепочке работ

**В исходниках.** RunSlot refcount удерживает один semaphore permit между chained runs, goal loop и internal rerun. settle не освобождает handle живого sync worker; interrupt ждёт shielded run до5s и не очищает unfinished task.

**Для Proteus.** Полезный pattern для будущего long-running driver: request acknowledgment, admission capacity, work lifetime и cleanup acknowledgment отдельно. Не освобождать capacity только потому, что waiter canceled.

**Граница вывода.** Это source pattern, не готовая замена Proteus admission; полный scheduling/goal-loop не покрыт.

Источники: [agent_server/event_service.py L112-L181](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/event_service.py#L112-L181), [agent_server/event_service.py L1477-L1521](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/event_service.py#L1477-L1521), [agent_server/event_service.py L1577-L1615](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/event_service.py#L1577-L1615), [agent_server/event_service.py L2115-L2141](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/event_service.py#L2115-L2141); [Core bound_tools/invocation.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/invocation.rs#L79-L113).

### ECO3-08. Crash recovery чинит transcript, не восстанавливает environment

**В исходниках.** Server startup гидратирует RUNNING records, не все idle conversations. EventService переводит stale RUNNING в ERROR, сканирует full log (HEAD может отставать), добавляет error для первого unmatched action и parent-ит его к action.

**Для Proteus.** Unknown operation outcome требует отдельного reconciliation с реальным target. Нельзя принимать recovery error за доказательство 'ничего не записано' и автоматически повторять side effect.

**Граница вывода.** Не исследованы все multiple-unmatched/remote branch случаи; источник сам отмечает отсутствие remote branching в этом пути.

Источники: [agent_server/conversation_service.py L2218-L2258](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/conversation_service.py#L2218-L2258), [agent_server/event_service.py L1421-L1472](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-agent-server/openhands/agent_server/event_service.py#L1421-L1472), [conversation/state.py L677-L716](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/state.py#L677-L716); [Core bound_tools/hooks.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/hooks.rs#L92-L130).

### ECO3-09. Parallel safety требует resource key, а не только имени tool

**В исходниках.** DeclaredResources различает unknown и explicit empty. Необъявленный resource сериализуется per tool:name; declared keys берутся в sorted order и освобождаются обратно, timeout/refcount обслуживаются отдельно. Каждый ParallelToolExecutor имеет собственный lock manager.

**Для Proteus.** Для общего browser/session хранилища lock key должен выражать сам ресурс и owner scope. В Proteus уже есть opt-in supports_parallel_tool_calls=false по умолчанию; сначала conservative module setting, не новый глобальный scheduler.

**Граница вывода.** Заявление tool о shared resource — доверенное описание, не OS isolation; межпроцессная сериализация этим классом не установлена.

Источники: [tool/tool.py L251-L280](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/tool/tool.py#L251-L280), [tool/tool.py L529-L537](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/tool/tool.py#L529-L537), [agent/parallel_executor.py L51-L65](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/agent/parallel_executor.py#L51-L65), [agent/parallel_executor.py L275-L357](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/agent/parallel_executor.py#L275-L357), [conversation/resource_lock_manager.py L84-L117](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/resource_lock_manager.py#L84-L117); [Core domain/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/domain/tool.rs#L283-L325).

### ECO3-10. Browser resource живёт шире отдельного tool

**В исходниках.** BrowserToolSet переиспользует class-level executor между parent/subagents, повторную executor_config логирует как ignored. Все browser tools используют один executor. close отделяет shared reference и очищает executor; BrowserToolSet.create при startup error возвращает пустой список.

**Для Proteus.** Будущий Proteus browser adapter должен явно различать owned/borrowed session, effective config и unavailable capability; логическое tool listing не должно обещать отдельный browser каждой conversation.

**Граница вывода.** Это исследование ownership pattern, не вывод о безопасности многопользовательского deployment; реальный browser не запускался.

Источники: [browser_use/definition.py L804-L892](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/definition.py#L804-L892), [browser_use/impl.py L689-L753](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/impl.py#L689-L753); [Core src/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-module-sdk/src/tool.rs#L35-L61).

### ECO3-11. Свежесть browser observation не равна актуальности selector

**В исходниках.** BrowserClickAction принимает index, описание требует актуальный get_state. Prompt guidance требует get_state перед каждым click/type; wrapper передаёт index напрямую browser-use. Observation хранит текст+screenshot, output может truncatе и сохраняться отдельно.

**Для Proteus.** Для детерминированного driver контракта нужны session generation и observation handle, а не только integer selector. exact quote/span из локального artifact реализуется сейчас без browser automation и не делает живую DOM state достоверной.

**Граница вывода.** Browser-use downstream здесь не переаудирован; отсутствие проверки observation revision установлено лишь в прочитанном SDK wrapper/schema.

Источники: [browser_use/definition.py L61-L135](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/definition.py#L61-L135), [browser_use/definition.py L202-L244](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/definition.py#L202-L244), [browser_use/definition.py L778-L787](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/definition.py#L778-L787), [browser_use/impl.py L563-L606](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/impl.py#L563-L606); [Core domain/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/domain/tool.rs#L86-L135).

### ECO3-12. Browser timeout recovery создаёт новую session, не replay старого результата

**В исходниках.** Executor считает последовательные timeout failures, использует shortened timeout перед третьим failure, затем best-effort cleanup/reset и lazy restart на следующем action. Обычные action errors не считаются browser crash. AsyncExecutor.close явно bounded best-effort, может оставить ресурсы до process exit.

**Для Proteus.** Любой recovery tool должен вернуть session changed/cleanup uncertainty; retry submit/click нельзя обосновать одним timeout. В Proteus cancellation metadata и raw effect recording уже есть, exact-once при внешнем browser transport отсутствует без driver reconciliation.

**Граница вывода.** Не подтверждается исчезновение Chromium/process descendants или успешность reset; это намеренная best-effort граница источника.

Источники: [browser_use/impl.py L388-L461](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/impl.py#L388-L461), [browser_use/impl.py L538-L546](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/impl.py#L538-L546), [browser_use/impl.py L673-L719](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-tools/openhands/tools/browser_use/impl.py#L673-L719), [utils/async_executor.py L117-L220](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/utils/async_executor.py#L117-L220); [Core bound_tools/hooks.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/hooks.rs#L92-L130).

### ECO3-13. Workspace pause, conversation close и OS isolation имеют разных владельцев

**В исходниках.** LocalWorkspace исполняет на host filesystem; pause/resume no-op. DockerWorkspace владеет созданным --rm контейнером, pause/unpause freezing отдельно от cleanup docker stop. LocalConversation.close освобождает agent/tools, а workspace lifecycle управляется своим context manager.

**Для Proteus.** Не называть remote/local abstraction sandbox. Proteus process boundary тоже не OS sandbox; использовать существующий explicit restricted launch, не расширять tool authority из-за browser/module бренда.

**Граница вывода.** Container isolation/security config целиком не проверен; cleanup command request не подтверждает externally observed removal.

Источники: [workspace/local.py L17-L80](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/workspace/local.py#L17-L80), [workspace/local.py L202-L216](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/workspace/local.py#L202-L216), [docker/workspace.py L234-L258](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-workspace/openhands/workspace/docker/workspace.py#L234-L258), [docker/workspace.py L353-L430](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-workspace/openhands/workspace/docker/workspace.py#L353-L430), [impl/local_conversation.py L2860-L2910](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L2860-L2910); [Core contracts/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/contracts/tool.rs#L20-L50).

### ECO3-14. Dynamic MCP catalog — scoped reconciliation, не безусловная регистрация

**В исходниках.** AgentBase.add_runtime_tools проверяет duplicate/conflict names; same-client updates разрешены. Reconciliation удаляет прежние tools только данного client и copy-on-write заменяет map; tools_map возвращает копию под lock. Restore verify проверяет class и отсутствие removed configured names, а не полную семантику schema/executor.

**Для Proteus.** Сохранить ownership каталога и execution snapshot. В Proteus model tool spec сверяется с registered spec и policy visibility; не добавлять module-specific обход или автоматический импорт чужой history.

**Граница вывода.** Runtime MCP updates и persisted explicit tools — разные пути. Full external MCP client/notification order не трассирован.

Источники: [agent/base.py L684-L750](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/agent/base.py#L684-L750), [agent/base.py L831-L901](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/agent/base.py#L831-L901), [agent/base.py L973-L1023](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/agent/base.py#L973-L1023), [impl/local_conversation.py L1400-L1449](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L1400-L1449); [Core core/bound_tools.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools.rs#L168-L243).

### ECO3-15. rerun_actions повторно производит реальные эффекты

**В исходниках.** LocalConversation.rerun_actions берёт ActionEvents из полного state.events и заново вызывает tools; источник предупреждает non-idempotence и reset workspace. Это не event projection и не read-only verification.

**Для Proteus.** Proteus workflow replay и citation verification не должны исполнять историю. Нужное reuse — explicit отдельный operation mode с host authorization, а не случайный fallback replay.

**Граница вывода.** В этом пакете rerun не исполнялся. Паритет с OpenHands как совместимый runtime не заявляется.

Источники: [impl/local_conversation.py L3078-L3181](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L3078-L3181); [Core bound_tools/hooks.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/hooks.rs#L125-L129).

### ECO3-16. Current Core1fc и published SDK3f различены, новый evidence DTO Core не требуется

**В исходниках.** Девять релевантных файлов contracts/SDK/BoundTools/conversation read побайтно одинаковы между 3f36a003 и1fc3ef2 и локальным baseline. Во всём contracts+SDK diff лишь AppServerEvent::SessionCatalogUpdated (3 строки). ConversationView schema1 и tool host callbacks уже существуют.

**Для Proteus.** evidence.verify_spans — ordinary ReadOnly tool/v6 с nested host read. Shared checked-read support — pure validation библиотека, не связь implementations и не новый slot. Коррекция memory/CAS остаётся отдельным не реализованным consumer.

**Граница вывода.** Source compatibility этого среза не заменяет реальные protocol/Core invocation tests. Implementation отдельно, после predesign review.

Источники: [Core src/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-module-sdk/src/tool.rs#L20-L32), [Core src/hosts.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-module-sdk/src/hosts.rs#L82-L123), [Core conversation/view.rs](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/contracts/conversation/view.rs#L1-L55).

## Что реализовать первым

### 1. `evidence.verify_spans`: аудит цитаты против local source artifact

Сценарий: исследователь подготовил вывод с точной цитатой из закреплённого файла. Оператор заранее связал `source_id` с разрешённым относительным путём. Tool независимо вызывает host `read_file`, проверяет strict full-read envelope, SHA256 всех наблюдавшихся UTF-8 bytes, затем nonempty half-open byte spans и точное равенство quote. Ответ содержит scoped witness, **`semantic_entailment=not_evaluated`**, **`origin_verified=false`**.

Один source/read buffer на invocation, 1–32 bounded claims. Не набор произвольных model-supplied paths; не привлечение модели для оценки истинности; не generic Hermes verification receipt. Путь файла, URL в комментарии и совпавший hash не удостоверяют автора или истинность цитируемого утверждения. Trusted reader/AfterTool цепочка остаётся trust boundary.

Практическое продолжение — отдельный source-reviewed модуль `evidence.verify_spans`; runtime status не выводится из этого исследования. Сквозной сценарий — [проверка research-цитаты](EVIDENCE-SPANS-RESEARCH-USECASE.md).

### 2. Browser/environment driver — только отдельное последующее предложение

Реальный сценарий: прочитать страницу, получить observation, подготовить заполнение формы, запросить host approval перед submit, при timeout показать unknown outcome и повторно наблюдать состояние вместо повторного submit. Минимально нужны effective environment identity/generation, owned vs borrowed lifetime, observation handle, exact action, host admission, outcome/cleanup states. Controller не вправе создавать собственный bypass policy. Произвольный integer selector и 'успешный close' без acknowledgment цели недостаточны.

Текущий пакет **не запускает browser**, не создаёт driver и не утверждает необходимость нового общего Core contract: сначала нужно проверить конкретный backend через existing tool/v6. BrowserUse/ADK round1 и Letta/Strands round2 не изменялись.

### 3. Memory correction/CAS — остаётся отдельным consumer proposal

Сценарий round2: old fact/revision → verified source quote → reviewable correction → host-authorized CAS → current projection. Quote tool поставляет только byte witness. Он не выдаёт grants, не меняет память и не обещает CAS, persistence или idempotency. Настоящие owner authorization, backend transaction, operation-key dedup, recovery и lost-ACK reconciliation должны быть определены отдельно.

## Граница shared helper

Practical owner подтвердил: общий helper должен быть pure checked-read validator над canonical ToolResult с explicit max_output_bytes. Он не вызывает host/FS/network, не знает JSON assertions или quote spans и не выдаёт provenance guarantees. Caller владеет rawcallback JSON cap, configured paths, host dispatch, cancellation и result budgets. Первоначальное размещение отдельным neutral support crate внутри нового workspace допустимо; frozen v1 и pending strict-pair не переписываются. Root/integration решают общий published layout и rerun обоих consumers при рефакторинге.

## Проверки и непокрытое

- Source hash verification:31/31; details source-manifest.json и hash-verification.txt.
- Core source comparison:9 релевантных файлов совпадают old/current/local; details core-baseline-comparison.json.
- Точные source ranges:coverage.json. Link/JSON/whitespace QA записывается в validation.json, не считается runtime test.
- Upstream tests, browser actions, model calls, container lifecycle, full crash matrix, чужой код и scripts: **не запускались**.
- Публиковать только безопасные report/ledger/proposal. Полные source snapshots и неподтверждённые частные вопросы не входят в этот публичный пакет.
