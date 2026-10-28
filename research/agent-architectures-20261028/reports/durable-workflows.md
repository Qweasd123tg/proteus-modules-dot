# Надёжное продолжение и управление ресурсами агентов Proteus

Проверено 28 октября 2026 года по официальной документации и закреплённым исходникам. Цель — выбрать расширения, которые сохраняют надёжность Proteus и не дублируют уже имеющиеся механизмы.

**Вывод:** LangGraph и Microsoft Agent Framework полезны как источники отдельных решений, а не как замена runtime Proteus. Приоритетные направления — явный неизвестный исход внешнего эффекта, проверка совместимости холодного продолжения и совместное резервирование ресурсов перед запуском готового шага. Это проектные предложения, а не реализованные возможности или обещание совместимости с донорами.

## Актуальность проектов

| Проект | Проверенное состояние | Закреплённый источник |
| --- | --- | --- |
| LangGraph | Активная линия. Проверен HEAD от 28 октября. | [5a3e5dd73982a8ac81fb2c71c15b22ca982838de](https://github.com/langchain-ai/langgraph/commit/5a3e5dd73982a8ac81fb2c71c15b22ca982838de) |
| Microsoft AutoGen | В официальном README обозначен архивированным и больше не поддерживаемым Microsoft; для новых проектов указан Microsoft Agent Framework. Не рассматривать AutoGen как текущую production-зависимость. | [README на d07c667a3239ea4ab7af62a53b0f4ff205a1f23d](https://github.com/microsoft/autogen/blob/d07c667a3239ea4ab7af62a53b0f4ff205a1f23d/README.md#L14-L31) |
| Microsoft Agent Framework | Актуальный преемник AutoGen; проверен текущий код checkpoint, restore и handoff. | [c2a8f91b3070596c30723f74f303a124332bbb77](https://github.com/microsoft/agent-framework/tree/c2a8f91b3070596c30723f74f303a124332bbb77) |
| Microsoft Agent Framework Durable Extension | Durable Task и Azure Functions вынесены в отдельный репозиторий. Текущий Python schema-v2 runtime на этой ветке прямо обозначен **unreleased**; его нельзя выдавать за выпущенную гарантию совместимости. | [Репозиторий на de35f65e5245086701a5dc3b8ba328a5b4a1849f](https://github.com/microsoft/agent-framework-durable-extension/blob/de35f65e5245086701a5dc3b8ba328a5b4a1849f/README.md), [статус runtime](https://github.com/microsoft/agent-framework-durable-extension/blob/de35f65e5245086701a5dc3b8ba328a5b4a1849f/python/packages/durabletask/README.md#L97-L156) |

Разделять три вещи: сохранённое состояние workflow, безопасное повторение внешнего действия и совместимость старого выполнения с новым кодом. Наличие первой не доказывает две остальные.

## Что в Proteus уже есть

Границы дополнительно сверены на Proteus-core [`125a9eb4088991513e9f61d899469be2076e266c`](https://github.com/Proteus-harness/Proteus-core/tree/125a9eb4088991513e9f61d899469be2076e266c).

- Canonical journal сохраняет факты выполнения; read-only workflow replay воспроизводит записанное без повторения реальных tools. `ToolExecutionRecorder` различает запрос, разрешение и результат; при активной hook chain `BoundTools::finish` сохраняет settled effect перед отменяемым AfterTool. Не нужен второй ledger. [Recorder](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/tool_execution_recorder.rs#L9-L53), [finish](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/bound_tools/hooks.rs#L92-L130)
- `ExecutionAdmission` уже захватывает immutable runtime snapshot и execution scope; hot-swap epochs защищают текущий turn. Это не отсутствующий admission вообще. [ExecutionAdmission](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/runtime/execution.rs#L19-L58), [hot-swap](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/docs/architecture/hot-swap.md)
- AgentControl уже ограничивает одновременные процессы роли semaphore. `ModelQuotaSnapshot` уже описывает наблюдаемую квоту провайдера, но не является резервированием ресурсов. [Process permits](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/agent_control/process/mod.rs#L89-L124), [quota DTO](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/model_quota.rs#L1-L44)
- Существующий Pi-inspired `planning.ready_steps` — ограниченный advisory DAG-анализатор с caller-supplied unverified statuses. Он не запускает узлы и не удостоверяет их завершение. Второй такой анализатор не нужен; его рекомендации нельзя автоматически считать разрешением на запуск. Hermes verification-прототипы также не требуют дублирующего общего verifier.

Процессная декомпозиция не требует замены. Новые алгоритмы должны использовать существующие slots; расширение host contract оправдано только той семантикой, которую эти slots сейчас не выражают.

## Явный исход внешнего эффекта

### Какой пробел закрывает effect settlement

Внешний сервис мог принять действие, а процесс — завершиться до записи результата. Journal завершённых calls не устанавливает, произошло ли такое незаписанное действие. Ошибка транспорта не доказывает отсутствие эффекта.

LangGraph восстанавливает завершённые task results, но начатая и незавершённая task может выполняться снова; официальные рекомендации требуют идемпотентности или сверки существующего результата. [Документация на abd531b4](https://github.com/langchain-ai/docs/blob/abd531b4c4d2625ac24ad1af0cb26d24aa6a3415/src/oss/langgraph/functional-api.mdx#L790-L810) Показательный текущий пример — SDK reconnect: первоначальный POST намеренно не повторяется, поскольку он мог уже создать run; повторное чтение stream имеет другую семантику. [Изменение LangGraph](https://github.com/langchain-ai/langgraph/commit/5a3e5dd73982a8ac81fb2c71c15b22ca982838de)

### Предлагаемый модуль

Небольшой pure Rust helper `effect_settlement` вычисляет допустимый следующий шаг, но не выполняет внешних действий. Host связывает стабильный `OperationKey` с execution identity, canonical arguments digest и выбранным export. Существующий journal получает явно выраженные переходы:

```text
Prepared → Dispatched → Settled
                 ↘ OutcomeUnknown
```

При восстановлении допускаются lookup сохранённой receipt, read-only сверка сервиса либо повтор с тем же provider idempotency key, если соответствующая гарантия сервиса действительно существует. Для неидемпотентного действия неизвестный исход не превращается в автоматический retry. Изменившиеся arguments при прежнем ключе отклоняются.

**Место интеграции:** существующие tool lifecycle records и `BoundTools`; provider-specific lookup остаётся внутри конкретного tool implementation. Это не новая база событий и не универсальная обёртка, делающая произвольный инструмент идемпотентным.

**Граница полномочий:** receipt доказывает известный исход, но не предоставляет разрешение. Повтор проходит текущие policy, approval, safety и cancellation. Нельзя восстанавливать grants из произвольного payload, выполнять recovery через привилегированный hook или автоматически запускать компенсацию.

**Стоимость и ограничения:** дополнительные durable переходы и индекс operation keys; хранение receipts отдельно от сокращаемого transcript; отдельная реализация reconciliation для каждого внешнего сервиса. Без участия внешней стороны нельзя обещать exactly-once. Начальный scope — один инструмент с проверяемой идемпотентностью, а не все tools сразу.

## Проверка совместимости холодного продолжения

### Какой пробел закрывает resume manifest

Одинаковое имя модуля не означает одинаковую реализацию. После рестарта могли измениться executable, topology, reducer или схема состояния. Живой snapshot epoch решает другую задачу.

MAF сохраняет `graph_signature_hash` и отклоняет restore при изменившейся topology. Signature включает типы executors, endpoints, имена conditions и вложенные workflows; это **не hash семантики исходников**. [Построение signature](https://github.com/microsoft/agent-framework/blob/c2a8f91b3070596c30723f74f303a124332bbb77/python/packages/core/agent_framework/_workflows/_workflow.py#L1319-L1384), [restore gate](https://github.com/microsoft/agent-framework/blob/c2a8f91b3070596c30723f74f303a124332bbb77/python/packages/core/agent_framework/_workflows/_runner.py#L288-L327)

В прочитанном Proteus `SessionConfigSnapshot` сохраняет schema version, module IDs, tools и настройки, но не artifact/workflow semantic digest. `WorkflowHistoryCheckpoint` описывает историю и bindings tool results, а не сериализованный стек произвольного алгоритма. [Config snapshot](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/config_snapshot.rs#L16-L31), [history checkpoint](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs#L47-L72)

### Предлагаемый модуль

Pure Rust `resume_manifest` строит canonical representation и digest:

```text
ResumeManifest
  workflow_contract
  workflow_semantics
  artifact_digest
  state_schema
  node_ids
  reducer_versions
  tool_schema_digest
```

Проверка возвращает `Exact`, `ExplicitMigrationRequired` или `Incompatible`. Начальный безопасный режим — diagnostic gate и отказ от холодного продолжения при несовпадении. Не добавлять автоматическую миграцию одновременно с первым manifest.

**Место интеграции:** приложение к существующему snapshot/journal и восстановлению workflow. Новый checkpoint store не нужен. Hash подтверждает совпадение перечисленных данных, но не доказывает корректность модуля или полноту manifest.

**Handoff:** при необходимости передавать bounded state capsule с manifest, journal cursor и typed pending step. Root-owned AgentControl остаётся владельцем identity, смены владельца и lifecycle. Не копировать credentials или grants. MAF synthetic handoff-tools являются внутренними routing signals, для которых framework специально отключает function approval; это не основание для аналогичного обхода в Proteus. [MAF handoff source](https://github.com/microsoft/agent-framework/blob/c2a8f91b3070596c30723f74f303a124332bbb77/python/packages/orchestrations/agent_framework_orchestrations/_handoff.py#L397-L410)

**Стоимость и ограничения:** линейное хеширование manifest, явное версионирование поведения и либо удержание прежнего artifact, либо отказ от resume. Полная миграция состояния и durable ownership transfer существенно дороже диагностического gate. Это не требование вечной обратной совместимости всех pre-release форматов Proteus.

## Совместное резервирование ресурсов

### Какой пробел закрывает multi resource admission

Несколько ready nodes могут одновременно исчерпать один provider budget или конкурировать за запись одного worktree. Готовность по dependencies, разрешённость действия и наличие ресурсов — три независимые проверки.

LangGraph использует обычный `max_concurrency` semaphore. Сам по себе такой порт ничего не добавит к уже существующим process permits Proteus. [LangGraph executor](https://github.com/langchain-ai/langgraph/blob/5a3e5dd73982a8ac81fb2c71c15b22ca982838de/libs/langgraph/langgraph/pregel/_executor.py#L143-L162)

### Предлагаемый модуль

Заменяемая pure Rust `AdmissionPolicy` принимает host-verified ready set, resource snapshot и demands; возвращает детерминированный план резервирования. Host атомарно резервирует весь необходимый набор, без удержания части ресурсов во время ожидания остальных:

- provider concurrency;
- ограниченный token reservation, если известна осмысленная верхняя граница;
- process slot;
- именованный exclusive write resource.

Начальная очередь — bounded FIFO с aging, стабильным порядком и явным отказом при превышении capacity. Ожидание отменяемо. Ресурс освобождается после подтверждённого окончания владельца; один истёкший таймер не доказывает, что старый процесс перестал писать. Разрешение lease по времени потребовало бы fencing, а не только TTL.

**Место интеграции:** перед фактическим dispatch существующего workflow/AgentControl, не внутри advisory `planning.ready_steps`. Состояния графа для enforcement должны происходить из host-owned execution facts. Первый независимый модуль может лишь моделировать admission; это нельзя выдавать за действующее ограничение runtime.

**Граница полномочий:** module рекомендует распределение; host задаёт ceilings, валидирует plan и выдаёт invocation-bound reservation. Resource grant не предоставляет filesystem/network authority. Нельзя объединять права разных exports одного component.

**Стоимость и ограничения:** простой ограниченный алгоритм требует `O(Q × R)` на рассмотрение очереди из `Q` requests и `R` resource classes. Появляются accounting reserved/actual usage, fairness и обработка потерянного владельца. Начать с concurrency и именованных write resources; не обещать точный денежный бюджет по приблизительной оценке токенов. Это проектная адаптация для Proteus, а не готовая функция LangGraph или MAF.

## Рекомендуемый порядок

1. **Resume manifest:** сначала диагностический gate, без автоматических миграций.
2. **Effect settlement:** до включения автоматического retry/resume внешних записей.
3. **Multi-resource admission:** когда реальный параллелизм требует общей защиты нескольких ресурсов.

LangGraph supersteps и per-task pending writes интересны как образец локального сохранения прогресса, но не обосновывают замену canonical journal Proteus. Аналогично MAF checkpoints не являются готовым решением всех external-effect races. Заменяемость алгоритма следует сохранять; durable факты, identity и authority остаются у host.

## Границы проверки

Выполнено чтение официальных исходников и документации. Исходный код, сборки, тесты и CI не запускались; удалённые репозитории не изменялись. Отсутствие конкретной возможности выведено из прочитанных границ и DTO, а не из полного формального доказательства по всему репозиторию. Производительность, crash recovery и совместимость предложений ещё не проверены исполнением. Числовые сроки внедрения не заявляются.
