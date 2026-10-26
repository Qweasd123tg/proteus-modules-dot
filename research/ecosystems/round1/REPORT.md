# Другие направления агентов: browser agency и resumable workflow
## Первый source-grounded проход: Browser Use + Google ADK

**Главный результат:** расширять Proteus стоит не набором новых специальных Core-slots, а реальными потребителями существующих контрактов: исследованием с проверяемой картой доказательств, браузерными действиями с привязкой к наблюдению и — только при доказанной потребности — долговременно приостанавливаемым workflow. Гибкость должна оставаться в модулях; admission, identity, authorization, факты эффектов, cancellation и settlement — у host.

Это не список продуктов и не сравнение рекламных возможностей. Ниже разобраны конкретные lifecycle/state/effect пути двух различающихся систем и сопоставлены уже существующие реализации Proteus. Browser Use выбран как агент над изменчивым внешним состоянием страницы; ADK — как event-driven workflow с параллелизмом, возобновлением и human input. Ранее в переданном baseline эти направления имели в основном навигационные/документальные ссылки, а не такой проход по исходникам.

### Источники и уровень доказательств

| Объект | Зафиксированная ревизия | Что сделано |
|---|---|---|
| Browser Use | `3df5806a0d097a1546d92c49bcf1b28c9972c3bd` | 10 точечных файлов, 7 содержательно прочитаны частично; 3 только получены/проиндексированы |
| Google ADK Python | `bf6739723c1b8b03bff8bb1e6ffada4d88098fcf` | 25 точечных файлов, 22 содержательно прочитаны частично; 3 только получены/проиндексированы |
| Proteus Core | `3f36a003b4f3fde2242fc80f7aedac00dd127d1d` | Повторно прочитаны соответствующие contracts/runtime/bound tools из имеющегося snapshot |
| Proteus modules | `04114bbe85f179895e2b8553b6169a284caaeae3` | Проверены существующие tool selection и memory provider/tools |

35 новых файлов занимают **828 416 байт** без каталоговых накладных расходов. Для каждого нового файла local Git blob hash совпал с blob hash GitHub connector и pinned Git tree. Полные clones, зависимости и builds не создавались. `source-manifest.json` содержит пути/hash/URL, `coverage.json` — точные окна чтения и исключения.

**Уровень доказательств — source inspection.** Никакой upstream код, скрипты, tests, браузер, реальные модели, действия с аккаунтами или внешние side effects не запускались. Новые модули этим проходом не реализованы; performance, compatibility и качество model output не измерены. 17 безопасных архитектурных наблюдений находятся в `public-ledger.json`; частные неподтверждённые reliability-гипотезы отделены и не предназначены для публикации.

## 1. Два разных lifecycle

### Browser Use: observation → action schema → model → sequential effects → history

1. Agent получает свежий browser state, собирает screenshot/context и формирует доступную схему действий с учётом текущего URL.
2. Модель выдаёт action sequence. Между стадиями есть pause/stop checks.
3. `multi_act` запускает последовательные действия через registry. Ошибка/done/явный sequence terminator или изменение URL/focus прерывает хвост.
4. Итог шага и model output попадают в history. Browser disconnect может привести к ограниченному ожиданию восстановления; shutdown отслеживает lifecycle.
5. Отдельный `rerun_history` снова запускает действия и старается переидентифицировать элементы. Это **не** read-only анализ журнала.

Предметная ценность — связать выбор действий с текущим наблюдением и не продолжать устаревшую серию после очевидного изменения страницы. Граница — старое наблюдение может устареть и без смены URL; retry после частичного эффекта не превращает последовательность в транзакцию. [Step/context](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L1014-L1161), [multi_act](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L2755-L2874), [rerun](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L3128-L3308).

### ADK: invocation → node/event loop → persistence → replay index → resume

1. Runner поднимает invocation/session и event pipeline. Новая реализация `Workflow` имеет явные node statuses, run IDs, interrupts и completion ordering.
2. Node запускается с собственным контекстом; выполняет tool/model/orchestration и выпускает events/state/artifact deltas.
3. Nonpartial event обрабатывается и передаётся session service **до** выдачи потребителю; producer получает backpressure.
4. При human input node становится `WAITING`; при resume completed paths могут fast-forward по сохранённым events, а unresolved/failed paths обрабатываются иначе.
5. При abort отменяются принадлежащие запуску tasks; dangling calls получают terminal responses/marker. Это фиксация lifecycle, не rollback уже выполненных эффектов.

Важная поправка к описаниям старых ADK: в закреплённой ревизии `SequentialAgent` и `ParallelAgent` уже помечены deprecated в пользу `Workflow`. Однако checkpoint events ещё не означают прямую загрузку полной runtime-машины из checkpoint: в `_workflow.py` есть TODO resume from checkpoint, а mutable loop state объявлен неперсистентным. [Workflow](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_workflow.py#L240-L425), [persist-before-yield](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/runners.py#L767-L837), [replay interception](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/utils/_replay_interceptor.py#L20-L220).

## 2. Что действительно переносить, а что уже есть

| Потребность | Внешний паттерн | Уже в Proteus | Реальная недостающая предметная часть |
|---|---|---|---|
| Контекстно-зависимые tools | URL-based action model; invocation toolset | `BeforeToolSelection`, narrow-only validation, phase/query-aware dynamic hook | Observation identity браузера, стратегия фаз research workflow |
| Безопасные эффекты | Confirmation gate; tool callback pipeline | Host-bound Allow/Ask/Deny, durable resolution до вызова, execution attribution | Consumer-specific receipt/reconcile для внешней операции |
| Поступательный прогресс | Event persistence + node checkpoints | Cumulative history checkpoint с revision/CAS и exact tool-result binding | Реальный research producer/consumer, а не caller-supplied статусы |
| Повтор/восстановление | Browser rerun; ADK fast-forward | Read-only canonical offline replay, interrupted history | Явно различённые recipe rerun, resume и reconciliation |
| Память | Summary и state namespaces | Context preparation/compaction, memory provider, remember/recall tools | Evidence revisions и transient workflow state не смешивать со stable facts |
| Параллельная работа | Branches, graph scheduling | Batch tools и ограниченный root→child agent control | Namespaced evidence и deterministic reducer |
| Human pause на дни | WAITING/interrupt events | Ask внутри активного tool invocation; same-root-turn continuation | Если нужен durable suspended terminal state — точечный новый host semantic contract |

Следовательно, «добавить tool selection, memory, replay, checkpoints или hooks» — неправильная рекомендация: эти механизмы уже есть. Существующий `workflow/v20` даёт host calls к context/model/tools/events; `tool/v6` подходит действиям, `context_provider/v4` — автоматическому read-only включению контекста. Новые search/memory/browser слоты Core не нужны. [Workflow contract](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow.rs#L26-L125), [checkpoint binding](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs), [tool selection](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/tool_selection.rs), [memory provider](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/provider.rs).

## 3. Наблюдения по исходникам
### ECO-B01 — Единое наблюдение для контекста и экспонирования действий

Browser Use перед шагом получает browser state, обновляет схемы доступных действий для текущего URL и собирает model input. Выбор инструментов согласован с текущей страницей, но само экспонирование не является разрешением эффекта.

**Для Proteus:** Расширять существующий фазовый tool-selection hook и связывать browser action с observation ID; не создавать новый Core slot для браузера.

**Ограничение:** Уже есть narrow-only selection. Новизна — предметный токен наблюдения и его проверка browser driver, а не ещё один selector.

[Источник 1](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L1088-L1161), [Источник 2](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/tools/registry/service.py#L519-L582). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/tool_selection.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/hook/tool-selection-hook/src/lib.rs#L26-L190).

### ECO-B02 — Остановка хвоста серии после смены страницы

multi_act исполняет действия последовательно; done/error/терминатор останавливают хвост, также сравниваются URL и focused target до и после действия.

**Для Proteus:** Browser workflow после потенциально меняющего страницу действия получает новое наблюдение; driver атомарно проверяет expected observation/target перед dispatch.

**Ограничение:** URL/focus — не доказательство неизменности DOM. Ошибка не доказывает отсутствия уже выполненного префикса. Поведение внутренних DOM-драйверов здесь не покрыто.

[Источник 1](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L2755-L2874), [Источник 2](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/tools/registry/service.py#L291-L327). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow.rs#L30-L37).

### ECO-B03 — Повтор браузерной истории — повтор эффектов, не диагностический replay

rerun_history снова выполняет действия, обновляет ссылки на элементы и имеет retry/recovery. Extraction и итоговый summary могут обращаться к модели.

**Для Proteus:** Разделять inspect replay, recipe rerun и resume незавершённого выполнения. Для мутаций recipe требует operation identity, receipt и reconciliation неизвестного исхода.

**Ограничение:** Нельзя назвать такой rerun offline/exactly-once. Proteus уже имеет read-only replay без конструирования реальных tools/providers; его нельзя незаметно превратить в повтор действий.

[Источник 1](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L3128-L3308), [Источник 2](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L3423-L3553). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/workflow_replay/mod.rs#L1-L100), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_failure.rs).

### ECO-B04 — Pause/stop и timeout — разные границы управления

Pause/stop меняют состояние и проверяются между стадиями/действиями; act применяет wait_for и превращает многие ошибки в ActionResult. Это не откат серверного действия и не физическая остановка произвольного sync callback.

**Для Proteus:** Сохранять Core cancellation/settlement. В browser result различать not_performed/performed/unknown; проверять поздний результат, не заявлять успех по одному cancel ACK.

**Ограничение:** Ни один инструмент или браузер не запускался; здесь только границы, видимые в исходниках.

[Источник 1](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L1014-L1087), [Источник 2](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L3942-L4029), [Источник 3](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/tools/service.py#L2178-L2266), [Источник 4](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/tools/registry/service.py#L232-L259). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/invocation.rs#L1-L135), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/tool.rs#L1-L158).

### ECO-B05 — Watchdog lifecycle отдельно от обычного data plane

Базовый watchdog пропускает lifecycle события независимо от disconnected circuit breaker. Crash watchdog отслеживает свои фоновые задачи и отменяет их при остановке; reconnect ожидание ограничено.

**Для Proteus:** Browser adapter должен владеть своим session supervisor, lifecycle control и tracked tasks; recovery не должен произвольно перезапускать пользовательские мутации.

**Ограничение:** Полный BrowserSession recovery не проверен. LISTENS_TO/EMITS в watchdog — описательная, не принудительная capability граница.

[Источник 1](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/browser/watchdog_base.py#L24-L190), [Источник 2](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/browser/watchdogs/crash_watchdog.py#L1-L336), [Источник 3](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L1245-L1318). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-module-protocol/src/authority.rs#L1-L180), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/invocation.rs).

### ECO-B06 — Навигационная политика, approval и sandbox — не одно

Security watchdog имеет pre-navigation check и post-navigation/new-tab обработчики; registry допускает обычные Python callbacks с injected browser/session context. Эти механизмы полезны, но не составляют отдельной изоляции callback.

**Для Proteus:** Отдельно задавать URL/navigation policy, разрешение конкретного эффекта и доверие к процессу/driver. Browser workflow выполняет каждый эффект через host-bound tools.

**Ограничение:** Не заявление об уязвимости upstream. Restricted export и отдельный процесс Proteus также нельзя называть полным OS sandbox.

[Источник 1](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/browser/watchdogs/security_watchdog.py#L35-L92), [Источник 2](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/browser/watchdog_base.py#L24-L77), [Источник 3](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/tools/registry/service.py#L331-L435). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-module-protocol/src/authority.rs#L1-L180).

### ECO-B07 — Сжатая память шага не заменяет журнал эффектов

MessageManager запускает compaction по периодичности и порогу символов; сохраняет ограниченную историю и summary. Ошибка суммаризации не должна стирать предыдущую память.

**Для Proteus:** Оставлять summary производной модельной проекцией, а tool receipts, source revisions и approval facts — в canonical host history.

**Ограничение:** Символы не равны точным токенам. Не предлагается новая память с нуля: Proteus уже имеет context preparation и memory provider.

[Источник 1](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/message_manager/service.py#L199-L306). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/checkpoint.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs), [Proteus 3](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/provider.rs).

### ECO-A01 — Новый Workflow — предметный граф, не только SequentialAgent

В закреплённом ADK уже есть Workflow с RUNNING/WAITING/COMPLETED, run IDs и replay индексацией. Старые SequentialAgent/ParallelAgent помечены deprecated в пользу Workflow, но остаются отдельные ограничения интеграции.

**Для Proteus:** Иметь модульный phased research workflow на существующем workflow/v20; отдельную durable suspension семантику обсуждать лишь для реального потребителя.

**Ограничение:** Наличие checkpoint events не означает checkpoint-native recovery: _workflow.py содержит TODO resume from checkpoint; runtime state восстанавливается из событий.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/agents/sequential_agent.py#L20-L95), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/agents/parallel_agent.py#L170-L253), [Источник 3](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_workflow.py#L240-L425), [Источник 4](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_node_status.py). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow.rs#L41-L125).

### ECO-A02 — Persist-before-deliver и backpressure на событиях

Runner обрабатывает и сохраняет nonpartial event до передачи потребителю; processed_signal освобождает producer после возобновления consumer. ParallelAgent также ждёт подтверждения потребления каждого события.

**Для Proteus:** Для research workflow завершать фазу только после host checkpoint ACK и точного tool-result binding. UI/progress event и устойчивое доказательство результата различать.

**Ограничение:** Долговечность append зависит от выбранного SessionService; in-memory backend не доказывает crash durability. В Proteus commit-before-ACK уже есть.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/runners.py#L767-L837), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/runners.py#L1512-L1542), [Источник 3](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/agents/parallel_agent.py#L45-L169). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/checkpoint.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs).

### ECO-A03 — Conversation branch isolation не означает state isolation

ParallelAgent разделяет branch/history, но использует общий session state. Tool batch отдельно собирает локальные deltas и merge изменённых контейнеров. Scoped app/user/session state и temporary state имеют разную persistence.

**Для Proteus:** У параллельных исследовательских веток отдельные immutable input/evidence namespaces; reducer делает явный детерминированный merge с conflict records.

**Ограничение:** Не переносить shared mutable dictionary как неявный контракт Core и не обещать transaction isolation на основании одного branch ID.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/agents/parallel_agent.py#L20-L253), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/flows/llm_flows/tools/_batch_executor.py#L20-L240), [Источник 3](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/sessions/state.py#L20-L190), [Источник 4](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/sessions/base_session_service.py#L130-L230). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/agent_control.rs#L1-L180), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs).

### ECO-A04 — Approval связан с исходным вызовом, а не свободным текстом

Confirmation parser связывает ответ с историческим function call, его ID/name/args, автором агента и current branch; повторно потреблённые подтверждения отфильтровываются до загрузки каталога. Shared caller применяет confirmation gate перед реальным tool_runner, если callback не дал ответ.

**Для Proteus:** Сохранять host-owned Allow/Ask/Deny и recorded resolution Proteus; pending human decision содержит строгую response schema, call identity и ревизию аргументов.

**Ограничение:** Trusted plugin callback может дать substitute response; это extension policy, не внешний receipt и не новая authority. Отдельный durable pending механизм не реализован в этом исследовательском раунде.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/flows/llm_flows/tools/_confirmation.py#L25-L406), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/flows/llm_flows/tools/_caller.py#L418-L650), [Источник 3](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/utils/_workflow_hitl_utils.py#L20-L150). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/domain/tool.rs).

### ECO-A05 — Abort sealing закрывает dangling calls, но не откатывает эффект

Runner cleanup отменяет и ожидает root task; synthesizer добавляет error responses к незавершённым вызовам текущей invocation и aborted marker, включая confirmation calls. В node runner уже полученное событие ставится в очередь до проверки abort.

**Для Proteus:** Разделять lifecycle terminal marker и фактический исход эффекта. После abort не возобновлять mechanically старые unresolved calls; unknown outcome передавать на reconciliation.

**Ограничение:** Synthetic aborted response не доказывает not_performed. ADK async cancellation не останавливает уже работающий произвольный sync callable в thread pool.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/runners.py#L839-L896), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/events/_abort_events.py#L20-L143), [Источник 3](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_node_runner.py#L378-L459). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/invocation.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs), [Proteus 3](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_failure.rs).

### ECO-A06 — Replay-граф требует стабильной идентичности и бюджета повторов

Workflow восстанавливает run IDs и порядок завершения из событий, fast-forwards завершённые outputs, reruns неуспешные ветки. Node runner явно предупреждает, что attempt count не сохраняется между resumes. Retry utils предотвращают умножение item retry budget повтором всего worker.

**Для Proteus:** Consumer-local graph digest, node input digest, durable attempt budget и receipt binding; граф не должен считать supplied status=completed доказательством.

**Ограничение:** Это проектные требования нового модуля, не заявление, что существующий Proteus continuation уже является durable графом или что обнаружен подтверждённый upstream exploit.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_workflow.py#L305-L425), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_workflow.py#L640-L770), [Источник 3](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/utils/_replay_interceptor.py#L20-L220), [Источник 4](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_node_runner.py#L144-L267), [Источник 5](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/utils/_retry_utils.py#L27-L127). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow.rs#L87-L125).

### ECO-A07 — Invocation cache каталога полезен только с явной freshness семантикой

BaseToolset по умолчанию кэширует prefixed tool list на invocation_id; get_tools может фильтровать по контексту. Поэтому state-sensitive набор в течение invocation требует продуманного отключения/инвалидации кэша.

**Для Proteus:** Разделять стабильный registered catalog, narrow exposure выбранной фазы и execution-time authority. Не обновлять permission semantics сменой красивой tool description.

**Ограничение:** Кэш — оптимизация, не capability grant. Benchmarks/catalog churn не запускались.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/tools/base_toolset.py#L30-L220). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/tool_selection.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools.rs), [Proteus 3](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/hook/tool-selection-hook/src/lib.rs#L26-L190).

### ECO-A08 — Инкрементальный event index вместо повторного полного анализа

Replay manager поддерживает индекс событий и дополняет его при сохранении prefix; при rewind/compaction строит заново. Есть связи parent/descendant и function-call ID для сопоставления ответов.

**Для Proteus:** Если профилирование нового evidence workflow обнаружит repeated scans, хранить revision-keyed derived index, инвалидируемый на compaction/rewrite. Источником истины остаётся журнал.

**Ограничение:** Это алгоритмический паттерн, не измеренное ускорение Proteus. Нельзя копировать проверку prefix без учёта собственной revision/CAS модели.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/utils/_replay_manager.py#L35-L186), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/utils/_replay_manager.py#L247-L368). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/workflow_replay/mod.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/checkpoint.rs).

### ECO-A09 — Raw result и callback projection надо хранить раздельно

ADK before callbacks могут отвечать без tool run, after callbacks могут заменить ответ, затем строится FunctionResponse event. Proteus уже сохраняет raw effect перед AfterTool и отделяет projected result.

**Для Proteus:** Evidence producer принимает только host recorded raw result binding; косметическое преобразование и summary не могут повышать verified/committed статус.

**Ограничение:** Не требуется убрать гибкие hooks. Требуется сохранить различие authority, observed effect и presentation.

[Источник 1](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/flows/llm_flows/tools/_caller.py#L508-L650), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_tool_node.py#L100-L290). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs).

### ECO-X01 — Нужен реальный research consumer, а не ещё один advisory planner

Исследованные browser и workflow системы дают реальные lifecycle паттерны для исследования документов и подготовки веб-форм; в Proteus уже есть workflow host methods, narrow selection, memory provider, checkpoints, read-only replay.

**Для Proteus:** Первый приоритет research.evidence_map: host read tools → source digest/ranges → claims → deterministic ref validation → checkpoint → output с пробелами/противоречиями. Browser recipe и durable HITL — отдельные потребители/контракты.

**Ограничение:** Новые модули в этом исследовательском раунде не реализованы. Existing pi-ready-steps анализирует caller statuses, не является durable executor. Memory remember_fact не следует использовать для transient workflow control.

[Источник 1](https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/agent/service.py#L1088-L1161), [Источник 2](https://github.com/google/adk-python/blob/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf/src/google/adk/workflow/_workflow.py#L240-L425). Уже имеющийся аналог: [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs), [Proteus 3](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/provider.rs), [Proteus 4](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/tools.rs).

## 4. Практические модули и минимальные контракты

### M1 — `research.evidence_map`: следующий реальный consumer, без нового Core slot

**Сценарий:** пользователь даёт набор регламентов, PDF-текстов, исследовательских материалов или продуктовых спецификаций и спрашивает: «Какие требования противоречат друг другу, что изменилось и какие выводы можно защищать источниками?»

**End-to-end путь:**

1. Принять явно разрешённый corpus/источники и структурированный вопрос; зафиксировать входной digest и лимиты.
2. Получить данные через уже сконфигурированные host read tools — не собственной скрытой сетью. Источники и их excerpts остаются недоверенными данными, не управляющими командами.
3. Нормализовать `EvidenceRecord { source_id, revision_or_digest, locator, excerpt, tool_result_binding }`. Если retrieval tool не гарантирует immutable revision, это явно отражается в record.
4. Отдельно построить `Claim { text, evidence_ids, confidence_or_status, counterevidence_ids }`. Модель предлагает связи, но не присваивает сама себе статус «проверено».
5. Детерминированно проверить существование всех evidence IDs, диапазоны, соответствие digest и лимиты; различать «источник подтверждает», «модель интерпретирует», «не подтверждено», «противоречит».
6. Зафиксировать cumulative canonical history/checkpoint и вернуть ответ с источниками, пробелами и конфликтами. `completed` фаза опирается на host-recorded tool result, не на произвольный JSON status.

**Минимум:** существующий `workflow/v20`; строгие module-local schemas; host read tools; checkpoint/result binding; budgets; deterministic reducer. Ни новый authority token, ни generic search slot, ни прямой вызов другого модуля не требуются. Получение источника не равно доказательству истинности его содержания.

**Честный первый этап:** offline fixture corpus + authored retrieval fixture + deterministic fake model через установленный интерфейс. Это проверит producer→evidence→consumer→checkpoint и ошибки ссылок, но не докажет качество live web research. Нужны проверки missing/duplicate source, stale digest, tool denied, cancelled before/after receipt, malformed model refs, conflicting evidence и потеря ACK. Тесты этого модуля здесь **ещё не написаны и не запускались**.

**Почему не дубликат:** существующий `pi-ready-steps` — advisory анализ caller-supplied статусов, а не такой executor; Hermes gate нуждается в достоверном producer. Совместимость evidence record с существующим producer надо согласовать, не изобретать второй несовместимый формат.

### M2 — `browser.observation_recipe`: действия, привязанные к свежему наблюдению

**Сценарий:** собрать параметры из разрешённых веб-страниц, подготовить форму заявки, показать точные поля пользователю; затем отдельное явно разрешённое submit. При reconnect не повторить отправку «на всякий случай».

**Необходимая предметная поверхность browser driver:**

- Observation: `session_id, target_id, observation_id/generation, url, observed_at, elements_or_locators`.
- Action: `expected_target, expected_observation_id, operation_key, operation, args`.
- Outcome: `not_performed | performed | unknown`, `new_observation_id`, evidence/receipt reference и объяснение отказа.
- Reconciliation: read-only lookup по stable operation identity, если конкретная система предоставляет такую возможность. Если не предоставляет, `unknown` должен оставаться неизвестным, а не превращаться в автоматический повтор.

Это **предложение tool-specific schema**, не новый обязательный Core contract. Проверка expected observation и dispatch должны быть одной логической операцией driver; check в before-hook с отдельным последующим click оставляет TOCTOU. Browser URL не заменяет observation revision. Веб-страница не выдаёт authority командой в DOM.

Workflow вызывает configured browser tools через host; навигационная policy, permission конкретной мутации и trust process/OS isolation задаются отдельно. Нельзя завернуть сотню произвольных внутренних эффектов в «один безопасный helper», скрыв их от host policy/recording. Публичное описание operation_key не обещает, что сторонний сайт поддерживает idempotency.

**Первый приемлемый инкремент:** readonly observation/recipe validator и authored driver fixture. Полноценное выполнение требует совместимого реального driver и отдельной проверки его snapshot/dispatch/receipt semantics. Этот проход не подтверждает наличия такого driver в текущем Proteus и не делает live browser actions.

### M3 — resumable `research.review_pipeline`: сначала consumer, потом контракт

**Сценарий:** batch документов → параллельное извлечение evidence → deterministic merge → human решение по конфликту → подготовленный итог. Human review может случиться после закрытия процесса, а один источник может требовать повторной загрузки без полного перезапуска.

Для выполнения **в одном активном root turn** можно использовать существующий workflow/checkpoint интерфейс. Но `WorkflowContinuation` в текущем Core — host-reviewed продолжение того же root turn без нового user admission; terminal response имеет только `Success | Error`. Называть это готовым общим durable suspend/resume было бы неверно. [Текущий контракт](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow.rs#L87-L125).

Если нужен pending state за пределами живого вызова, прежде реализации потребуется узкое host-owned уточнение:

- стабильные execution/owner/request identities;
- phase/graph digest и input revision;
- строгая response schema, expiry и cancellation owner;
- `Suspended` либо эквивалентная terminal/pending семантика;
- persisted pending record до ACK, resume CAS, dedup ответов;
- late response после cancel/expiry не возрождает выполненный/запрещённый вызов;
- retry budget живёт через resume, graph changes не запускают случайно старый префикс заново;
- completed node основан на receipt; unknown не автоматически retryable.

Это не основание для широкого Core rewrite, межагентного mesh или сериализации произвольных closures. Existing root→child ограничения не расширяются модулем по собственной инициативе. Общий durable workflow engine без такого потребителя сейчас менее полезен, чем M1.

## 5. Как сохранить надёжность, не задушив гибкость

1. **Policy в модуле, authority у host.** Модуль выбирает research phases, summary style, graph topology и tool exposure. Host проверяет зарегистрированный tool, permission, execution identity и effect recording.
2. **Observation не authorization.** Схема, выбранная по URL/фазе, уменьшает ошибки модели, но не разрешает submit/send/delete.
3. **Presentation не receipt.** Callback, summary, source excerpt и модельное «готово» не заменяют raw tool result. Proteus уже сохраняет raw effect перед AfterTool; это достоинство, которое нужно не потерять при заимствовании.
4. **Cancel не rollback.** Отмена задачи/ожидания, закрытие websocket и прекращение наблюдения не дают доказательства, что внешний эффект отсутствует.
5. **Resume не blind rerun.** Отдельные операции inspect replay, rerun recipe, resume pending и reconcile unknown имеют разные разрешения и требования.
6. **Branch не transaction.** Параллельные агенты могут иметь отдельные conversation branches, но общую mutable state. Новый consumer должен задать merge/conflict rules явно.
7. **Оптимизация не гарантия.** Invocation catalog cache, summary и replay index имеют пользу только с определённой invalidation/freshness семантикой. Ускорение нужно измерять отдельно.
8. **Trusted extension остаётся trusted.** Dynamic callbacks и process modules дают расширяемость; ни язык Rust, ни отдельный процесс сами по себе не обеспечивают OS/network isolation.

## 6. Что ещё не покрыто

Не проверены полный BrowserSession/DOM/CDP action pipeline, истинная browser generation/locator semantics, production database backends ADK, все graph isolation/validation пути, модельные providers, поведение реальных сайтов, hard-kill synchronous plugins и распределённая crash durability. Шесть полученных файлов только проиндексированы, не выдаются за аудированные. Старые upstream docs не использованы вместо исходников новой реализации.

**Следующее наиболее полезное направление — Letta source:** долговременная память как редактируемые/прикрепляемые blocks, revision/attach-detach semantics, tool-mediated writes, контекстный budget и восстановление после concurrent updates. Нужен не обзор «у них есть память», а сравнение со стабильными фактами `memory-pack`, context_provider и существующим evidence-blocks примером: что действительно отсутствует и какой consumer оправдывает расширение. OpenHands SDK целесообразен следующим после этого лишь для browser/computer event/action boundaries, не ещё одного повторения coding loop.

### Файлы пакета

- `REPORT.md` — этот безопасный пользовательский обзор.
- `public-ledger.json` — 17 source-pinned наблюдений, аналоги Proteus, tradeoffs и статус.
- `coverage.json` — точные диапазоны чтения, source-only ограничения.
- `source-manifest.json` — 35 immutable source records с hash-проверкой.

**Итог:** самый дешёвый полезный шаг — реальный research evidence workflow на уже существующих контрактах. Browser agency требует прежде всего observation/action/unknown-outcome дисциплины driver, а не нового Core slot. Durable human-in-the-loop полезен, но его нельзя «реализовать» переименованием обычного continuation.
