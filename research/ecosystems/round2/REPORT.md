# Память как изменяемое состояние: Letta и Strands
## Второй source-grounded проход для Proteus

**Вывод:** интересный следующий модуль — не ещё один `Block { id, revision, text }` и не ещё один selector. Нужен законченный сценарий **«найти факт → проверить точную цитату → предложить исправление → применить по ожидаемой ревизии → показать актуальную память»**. Он использует уже существующие Core contracts, но требует настоящего producer, mutable store и consumer с честной семантикой. Исходный текст, модельная интерпретация, факт записи и попадание в следующий prompt — четыре разные вещи.

Этот проход дополняет, но **не изменяет** первый Browser Use / ADK batch.

### Важная актуализация источников

На актуальном `letta-ai/letta` main больше нет старого сервера: закреплённый README называет его retired V1, указывает `archive` и перенаправляет активную разработку в `letta-ai/letta-code`. Поэтому ниже **исторические Block/BlockHistory** и **актуальные MemFS/worktree механизмы** строго разделены. Для Strands GitHub metadata перенаправляет прежнее имя `sdk-python` в `harness-sdk`; исследована Python часть нового monorepo, а не предположена старая структура. [Letta source routing](https://github.com/letta-ai/letta/blob/8816d3a8516893bfdc0fa14bfb1235226012e295/README.md).

| Источник | Pin | Получено / содержательно прочитано частично |
|---|---|---:|
| Letta navigation main | `8816d3a8516893bfdc0fa14bfb1235226012e295` | 1 / 1 |
| Letta V1 **archive** | `56ba9c25552605eec89de8ed3dc6394b625c1993` | 11 / 9 |
| Letta Code active | `1fb6ea4d30942ef9220b096ba7f4185f18184fc1` | 21 / 19 |
| Strands harness-sdk | `10b9393ef705ccf4b56e5fe0d81e0712c0d97efe` | 13 / 13 |

Итого **46 точечных файлов, 1 084 064 байта**, 42 частично source-reviewed, 4 только fetched/indexed. Все local Git blob hashes совпали с GitHub connector и pinned tree. Это не полный audit четырёх репозиториев. Точные пути и окна чтения: `source-manifest.json`, `coverage.json`.

Core сравнивался на `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`, modules на `04114bbe85f179895e2b8553b6169a284caaeae3`. Дополнительно прочитаны прежний read-compat proof, опубликованный evidence-blocks example и source-reviewed json_contracts producer — без изменения или запуска.

**Не выполнялись:** upstream код, hooks, scripts, test suites, реальные модели, browser/network actions, Git sync/clone исследуемых приложений, обращения к credential/account данным. Новые модули в этом исследовательском раунде не реализованы; correctness/performance/compatibility assertions не подтверждены runtime. Hash-проверка удостоверяет соответствие локального текста source pin, а не безопасность или истинность содержимого.

## 1. Три архитектуры памяти — не одна «общая память»

### A. Retired Letta V1: shared block → ORM update → history checkpoint → prompt projection

- Block имеет стабильный ID/label/value, может быть связан с несколькими agents.
- ORM version участвует в concurrency control; отдельная история предоставляет undo/redo snapshots.
- Attachment — связь, не копирование блока. В отдельных sleeptime сценариях attach затрагивает paired agent.
- После изменения block перестраиваются prompts подключённых agents; content commit и refresh имеют разные failure paths.
- Git-enabled вариант старого сервера прямо называет Git источником истины, PostgreSQL — быстрым cache. Его нельзя смешивать с обычным ORM update.

Полезный урок: **объект памяти, его membership, history и projection должны иметь отдельные identities и outcomes**. Старый интерфейс `BlockUpdate` не становится клиентским CAS лишь потому, что ORM имеет version column. [ORM/history](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/orm/block.py#L55-L69), [checkpoint](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/services/block_manager.py#L842-L912), [attach/detach](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/services/agent_manager.py#L2162-L2231).

### B. Current Letta: working tree → commit → merge/sync → compiled root memory + deferred reads

Актуальная MemFS v2 раскладывает память иерархически: root files видны в system projection, глубже лежат deferred documents с `MEMORY.md` индексами. Worker получает private worktree и отдельный read-only transcript handoff; готовые commits интегрируются, синхронизируются, затем обновляется prompt. Conflict repair — отдельный режим на parent checkout.

Неприятные результаты не сводятся к одному boolean: локальное изменение может быть committed, remote push — failed, prompt recompile — failed, а worker report — unsuccessful. Такой split полезнее ложного «ничего не произошло». **Но конкретный режим discard private worktree не означает отмену любых side effects child.** [Memory worker](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/subagents/memory-worker.ts#L80-L255), [integration outcomes](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/memory-worktree.ts#L668-L748), [deferred reads](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/tools/impl/memory.ts#L243-L422).

### C. Strands: independent memory stores + background extraction + injection middleware

Strands отделяет durable session state от memory stores. MemoryManager предоставляет search/add tools, automatic extraction и model-input injection. Per-store extraction chains имеют process-local watermarks, retry/backoff и flush; stores могут независимо завершиться успешно или ошибкой. Retrieval не переписывает durable conversation history.

Параллельно SnapshotSessionManager сохраняет snapshots агента; checkpoint marker лишь отмечает границу ReAct cycle. Это три разные сущности: **memory fact**, **session snapshot**, **pause marker**. Ни одна автоматически не является authority/effect journal. [Memory add/flush](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/memory/memory_manager.py#L512-L605), [extraction](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/memory/extraction/coordinator.py#L59-L266), [checkpoint distinction](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/experimental/checkpoint/checkpoint.py).

## 2. Что уже есть в Proteus — проверка против реального кода

| Компонент | Подтверждённая существующая возможность | Чего этим ещё не доказано |
|---|---|---|
| `ConversationSnapshot` / `ConversationView` | Canonical messages + model_context + revision; versioned read-only envelope source/session/projection | Full historical archive, external attachment bytes, безопасный admission чужих System/Tool records |
| `memory-pack` | `remember_fact`/recall и automatic read-only context provider; JSONL append | Replace/retract по object ID, expected-revision CAS, merge conflict handling |
| `letta.evidence_blocks` example | Scope, supplied revisions/tombstones, deterministic bounded selection | Persistent database, authenticated provenance, edits или источник истины |
| Старый read-compat proof | Reporting-only adapters + `visible_text`/`tool_report`, честные unsupported outcomes | Quote/hash/span matching, production parser/admission, authoritative foreign receipts |
| Новый `verification.json_contracts` producer | Host-bound full read, строгая проверка metadata/limits, SHA-256 observed bytes и реальные assertions | Raw-disk authentication, atomic multi-file snapshot, semantic entailment, quote spans |
| Core BoundTools / checkpoints | Host permission/admission/identity, raw effects перед AfterTool, cancellation settlement и checkpoint bindings | Truthfulness arbitrary memory backend или automatically safe retry внешнего эффекта |

**Актуализация старого readcompat вывода:** его рекомендация «пока не нужен новый ConversationView» относится к другому pin. В проверенном текущем Core **ConversationView уже существует** в `contracts/conversation/view.rs`, причём использует полный canonical snapshot, а не параллельную модель диалога. Поэтому дальнейший модуль должен переиспользовать его и предметные locators, не предлагать новый общий DTO. [View](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation/view.rs), [snapshot](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation.rs#L16-L70), [read lock order](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/conversation.rs).

Содержимое памяти остаётся данными. Изменение предпочтения «отвечать по-русски» и изменение permission policy «разрешить отправки» — не один класс записи; второе нельзя получить автоматическим memory distillation из transcript.

## 3. Source-pinned наблюдения
### ECO2-01 — Текущий Letta — не прежний V1, Strands сменил канонический репозиторий

Текущий letta-ai/letta main является навигационной страницей: активный код в letta-code, V1 обозначен retired/archive. GitHub metadata для sdk-python возвращает strands-agents/harness-sdk; Python исходники теперь в strands-py/.

**Перенос в Proteus:** Отдельно закреплять active и historical source. Не выдавать старые block APIs за современную MemFS архитектуру и не обещать совместимость по названию бренда.

**Граница доказательства:** Переименование подтверждено metadata; описание Letta migration — pinned README. Это не полноценный migration guide.

[Источник 1](https://github.com/letta-ai/letta/blob/8816d3a8516893bfdc0fa14bfb1235226012e295/README.md). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation.rs#L16-L70).

### ECO2-L01 — История block — отдельная сущность от API revision и trusted evidence

V1 ORM Block имеет version_id_col для optimistic locking; BlockHistory содержит sequence_number и checkpoint snapshots. После undo новый checkpoint удаляет будущую redo-ветвь. Public Block/BlockUpdate не передают этот ORM version как expected revision.

**Перенос в Proteus:** Memory correction consumer должен явно требовать expected revision/content digest. Нельзя считать supplied revision старого evidence-blocks примером реальной optimistic concurrency или неизменяемым audit log.

**Граница доказательства:** Только archived V1. Полный ORM/session transaction backend не запускался; наличие version column не доказывает клиентский compare-and-set.

[Источник 1](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/orm/block.py#L55-L69), [Источник 2](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/services/block_manager.py#L842-L912), [Источник 3](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/schemas/block.py#L67-L145). [Proteus 1](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/lib.rs#L84-L158), [Proteus 2](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks/src/lib.rs#L31-L151).

### ECO2-L02 — Attach/detach меняет участие памяти, а не существование всех её копий

V1 attach связывает agent с существующим Block и может прикрепить его sleeptime peer; detach удаляет связь только выбранного agent. Текущий shared-memory attach отдельно ждёт видимость API, создаёт local mount и перекомпилирует prompt; detach явно оставляет mount на диске.

**Перенос в Proteus:** Для memory scope/attachment хранить membership отдельно от content revision. UI должен раздельно сообщать detached, локальные bytes остались и projection refresh не удался.

**Граница доказательства:** Не обещать erase/forget-all по detach или tombstone. Современный cloud server ACL/attachment transaction не покрыт.

[Источник 1](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/services/agent_manager.py#L2162-L2231), [Источник 2](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/orm/blocks_agents.py), [Источник 3](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/cli/subcommands/shared-memory.ts#L304-L407). [Proteus 1](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks/README.md), [Proteus 2](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/lib.rs#L84-L158).

### ECO2-L03 — Изменённая память и обновлённый prompt — разные outcomes

V1 block update затем перестраивает prompts подключённых agents; ошибки rebuild логируются. Текущий memory worker после merge/sync вызывает recompile, но ошибка recompile не отменяет committed memory; shared-memory command сообщает recompile_failed отдельно.

**Перенос в Proteus:** У module store разделять committed_revision и projected_revision/refresh status. Повторять projection refresh, а не повторно применять уже записанное изменение.

**Граница доказательства:** Это наблюдаемый lifecycle split, не доказанная рассинхронизация в live deployment. Не менять host effect outcome из-за косметического refresh.

[Источник 1](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/services/block_manager.py#L61-L68), [Источник 2](https://github.com/letta-ai/letta/blob/56ba9c25552605eec89de8ed3dc6394b625c1993/letta/services/block_manager.py#L211-L270), [Источник 3](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/subagents/memory-worker.ts#L88-L111), [Источник 4](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/cli/subcommands/shared-memory.ts#L194-L210). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_failure.rs).

### ECO2-L04 — Прогрессивная память: индекс в контексте, детали по запросу

Текущий MemFS v2 compiler включает root memory и ссылки на child MEMORY.md; Memory tool читает deferred directory/file, показывает listing/description и явные truncation notices. Root files отклоняются этим tool как уже включённые в prompt.

**Перенос в Proteus:** Для большой проверяемой базы знаний — маленький context_provider индекс и read tool для конкретного документа. Budget и completeness должны входить в результат; retrieved content не становится system policy.

**Граница доказательства:** Это не новая категория Core slot и не измеренное снижение токенов. Existing evidence-blocks уже умеет bounded lexical selection, но не является persistent lazy store.

[Источник 1](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/backend/local/system-prompt-compilation.ts#L81-L143), [Источник 2](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/backend/local/system-prompt-compilation.ts#L154-L199), [Источник 3](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/tools/impl/memory.ts#L133-L177), [Источник 4](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/tools/impl/memory.ts#L243-L422). [Proteus 1](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/provider.rs), [Proteus 2](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks/src/lib.rs#L189-L248).

### ECO2-L05 — Рабочая память, committed memory и процитированный источник — разные представления

Local prompt compiler читает committed Git contents и возвращает memfsRevision; Memory tool читает рабочую файловую проекцию и может обрезать вывод. Присутствие revision/source строки само по себе не связывает любую цитату с конкретными immutable bytes.

**Перенос в Proteus:** Quote verifier должен проверять hash именно прочитанных bytes, точные UTF-8 spans и выбранную projection. Для committed view все reads должны быть на закреплённой revision, а не на подвижном имени.

**Граница доказательства:** Никакой цитатный hash не подтверждает истинность текста. Точная snapshot-consistency текущего Letta при concurrent writers не проверялась и остаётся непроверенным вопросом.

[Источник 1](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/backend/local/system-prompt-compilation.ts#L65-L143), [Источник 2](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/tools/impl/memory.ts#L330-L422). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation.rs#L16-L70), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation/view.rs).

### ECO2-L06 — Memory worker изолирует предложение до интеграции, но не маскирует поздний результат

Update worker создаёт private worktree, запускает worker, интегрирует commits и sync. Cancelled update discard не переносит его edits в parent; exception после commit сохраняет commits для интеграции, сохраняя failed task result. Merge conflict удерживает branch; repair worker работает непосредственно на parent checkout.

**Перенос в Proteus:** Для memory correction полезны proposal→validate→CAS apply→projection, а не автоматическое изменение global memory из контекста. Failure задачи не должен стирать факты уже совершённой записи; cancel и repair имеют разные гарантии.

**Граница доказательства:** Гарантия discard относится к этому локальному worktree пути, не к произвольным внешним эффектам child. Shared Git common dir и process tools не являются сами по себе sandbox.

[Источник 1](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/subagents/memory-worker.ts#L174-L255), [Источник 2](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/memory-worktree.ts#L125-L211), [Источник 3](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/memory-worktree.ts#L668-L748). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/invocation.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs).

### ECO2-L07 — Ownership token защищает cleanup от устаревшего worker

Memory operation lock сериализует harness writers; primary edits явно не используют этот lock. Repair marker имеет signature/token/state и переходы сравнивают token; dead-owner detection отличает живой paused процесс от умершего. Shutdown ожидает teardown tracked memory tasks.

**Перенос в Proteus:** В background producer нужен единый owner, generation/token на transition и drain/settlement. Не превращать истечение времени в доказательство, что writer умер, и не освобождать чужую новую lease.

**Граница доказательства:** Файловая lock/liveness реализация только прочитана частично; не доказан distributed lock. Core cancellation/settlement остаются host-owned; module lock не расширяет authority.

[Источник 1](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/memory-operation.ts), [Источник 2](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/memory-conflict-repair.ts#L107-L235), [Источник 3](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/utils/file-lock.ts#L66-L139), [Источник 4](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/tools/impl/memory-task-lifecycle.ts#L172-L233). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/invocation.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/agent_control.rs).

### ECO2-L08 — Валидация committed memory должна повторяться после объединения

Memory tree validator проверяет обязательные индексы, regular files, глубину, per-file/core character budgets и readOnlyFiles относительно accepted tree. Post-turn sync различает dirty/conflict/invalid/push_failed и повторяет validation после rebase.

**Перенос в Proteus:** Memory storage module должен проверять итог объединения/CAS commit, а не только каждое предложение отдельно. Лимиты не разрешаются моделью; read-only данные сравниваются с accepted revision.

**Граница доказательства:** Проверки characters не равны token budget. Предлагается собственный ограниченный memory backend, не выполнение Git hooks/upstream scripts.

[Источник 1](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/memory-constraints.ts#L39-L187), [Источник 2](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/memory-git.ts#L1837-L1982). [Proteus 1](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/lib.rs#L84-L158), [Proteus 2](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks/src/lib.rs#L84-L151).

### ECO2-L09 — Handoff как read-only evidence, не копия всех инструкций

Memory handoff постранично экспортирует parent transcript, исключает reasoning/system messages, создаёт отдельный read-only файл и удаляет его после child lifetime. Prompt просит использовать transcript только для конкретной неопределённости; repair-only worker обходится без transcript.

**Перенос в Proteus:** Использовать уже существующий conversation snapshot для scoped evidence extraction; передавать selected facts/locators, не runtime authority. Imported role/system text не должен становиться executable history.

**Граница доказательства:** Фильтрация roles и chmod не доказывают защиту от смысловой prompt injection. Полный export может быть крупным; в consumer нужны собственные лимиты, revision и completeness.

[Источник 1](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/agent/subagents/memory-handoff.ts). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation.rs#L16-L70), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/conversation.rs).

### ECO2-L10 — Context pressure требует проверки прогресса и безопасной границы

Local Letta compaction имеет guard уменьшения message count или estimated tokens, сохраняет pending tool-call tail в all mode и выбирает допустимый cutoff в sliding mode. Compaction представлена отдельной transcript entry с firstKeptEntryId, а не только заменённым текстом.

**Перенос в Proteus:** Сохранять host preparation/compaction и canonical execution facts. Module-memory limits и conversation compaction — разные бюджеты; fallback summary не превращается в receipt.

**Граница доказательства:** Token counts оценочные; нет benchmark. Полная crash durability LocalStore и model compaction quality не проверены.

[Источник 1](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/backend/local/compaction.ts#L62-L94), [Источник 2](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/backend/local/compaction.ts#L598-L709), [Источник 3](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/backend/local/local-store.ts#L1143-L1224), [Источник 4](https://github.com/letta-ai/letta-code/blob/1fb6ea4d30942ef9220b096ba7f4185f18184fc1/src/backend/local/local-store.ts#L3001-L3029). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/checkpoint.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs).

### ECO2-S01 — Accepted и stored различены; flush не универсальный commit ACK

Strands add_memory с wait_for_writes=false возвращает accepted и запускает tracked background writes, по умолчанию ожидает и возвращает stored. MemoryManager.flush обслуживает automatic extraction, но явно не ждёт fire-and-forget add. Sync Agent entrypoint вызывает flush в finally; async caller должен выбрать shutdown boundary.

**Перенос в Proteus:** Для durable memory mutation через Proteus tool возвращать actual write outcome/receipt, не accepted как успешную запись. Если нужен accepted job — отдельный статус и наблюдаемый terminal settlement.

**Граница доказательства:** Flush swallowing failures не даёт verified success. Это осознанная best-effort memory policy, не подтверждённая уязвимость.

[Источник 1](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/memory/memory_manager.py#L512-L605), [Источник 2](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/memory/memory_manager.py#L767-L775), [Источник 3](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/agent/agent.py#L1008-L1020). [Proteus 1](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/tools.rs#L40-L100), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs).

### ECO2-S02 — Extraction pipeline — producer с watermark, retries и частичными внешними writes

Coordinator сериализует saves каждого store, хранит in-memory message sequence/watermarks, rollback mark при обычной ошибке, backoff/probe и trim по минимальному mark. Extracted entries пишутся параллельно; при частичной ошибке весь batch повторяется, исходник прямо требует ожидать duplicates.

**Перенос в Proteus:** Новый memory distiller должен иметь persisted source revision/range, idempotency key и явный ledger accepted/applied/unknown; failed store не должен удерживать неограниченно все messages без quota.

**Граница доказательства:** Не обещать global at-most-once или crash recovery по process-local marks. Полная семантика cancellation и cross-process recovery требует отдельной проверки.

[Источник 1](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/memory/extraction/coordinator.py#L59-L266), [Источник 2](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/memory/extraction/coordinator.py#L269-L366). [Proteus 1](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/lib.rs#L84-L158), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs).

### ECO2-S03 — Snapshot, checkpoint marker и journal дают разные гарантии

Strands checkpoint содержит position/cycle/schema, а не conversation state. Snapshot сохраняет выбранные поля messages/state/conversation manager/interrupt/model state; session manager добавляет system prompt. RepositorySessionManager отдельно ведёт messages и agent state.

**Перенос в Proteus:** Не импортировать чужой snapshot как host admission или approval. Для read research использовать canonical snapshot/view; pause marker не выдавать за durable effect journal.

**Граница доказательства:** Storage/schema validation не удостоверяет источник. Snapshot не сохраняет произвольные tools/callbacks/OS effects; full graph scheduler не исследован.

[Источник 1](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/experimental/checkpoint/checkpoint.py), [Источник 2](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/types/_snapshot.py), [Источник 3](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/agent/agent.py#L2230-L2320), [Источник 4](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/session/repository_session_manager.py#L83-L196). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation.rs#L16-L70), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation/view.rs), [Proteus 3](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/workflow_replay/mod.rs).

### ECO2-S04 — Один capture, immutable history перед latest, но не единая внешняя транзакция

SnapshotSessionManager при trigger захватывает state один раз и сначала записывает immutable snapshot, затем latest. Save идёт также после invocation management; ошибка custom trigger не отменяет latest save. LocalFileStorage делает temp→replace; indexing может завершиться ошибкой после успешной записи bytes.

**Перенос в Proteus:** Кэш/индекс/проекция должны восстанавливаться из committed data; surfaced error не равен отсутствию write. Не копировать snapshot whole-state вместо существующего canonical journal Proteus.

**Граница доказательства:** Atomic rename не доказывает power-loss durability или cross-process CAS. Backend implementations/конкурентные writers не тестировались.

[Источник 1](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/session/snapshot_session_manager.py#L596-L692), [Источник 2](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/storage/local_file_storage.py#L114-L157). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/checkpoint.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs).

### ECO2-S05 — Ссылка на offloaded content требует availability/completeness

Snapshot save включает ephemeral stash inline или external reference для durable stash; ошибку snapshotting stash не скрывает. Restore stash, напротив, предупреждает и продолжает, если payload недоступен/несовместим.

**Перенос в Proteus:** Evidence consumer обязан отличать ref-present от bytes-resolved. Missing reference делает соответствующую проверку unsupported/incomplete, а не successful empty proof.

**Граница доказательства:** Это явный tradeoff availability против полноты. Не требуется новый всеобщий Conversation DTO; нужен узкий resolver, если concrete source использует external payload.

[Источник 1](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/session/snapshot_session_manager.py#L694-L760). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation/view.rs), [Proteus 2](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks/README.md).

### ECO2-S06 — Resume фильтрует уже полученные results, hooks остаются доверенными

Interrupt state сохраняет assistant request и completed_tool_results; при resume исполняются только IDs без результата. Executor поддерживает replace/short-circuit/retry callbacks; cancel прекращает retry, concurrent executor отменяет и ожидает принадлежащие tasks.

**Перенос в Proteus:** Effect facts хранить независимо от mutable hook projection и aggregate completion. Любой retry мутации требует consumer-specific доказательства допустимости; сохранить имеющиеся raw-effect и cancellation гарантии Core.

**Граница доказательства:** Наличие completed result не означает внешнюю exactly-once транзакцию. Полный background-task runtime и универсальная approval policy Strands здесь не покрыты.

[Источник 1](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/event_loop/event_loop.py#L817-L1030), [Источник 2](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/tools/executors/_executor.py#L212-L433), [Источник 3](https://github.com/strands-agents/harness-sdk/blob/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe/strands-py/src/strands/tools/executors/concurrent.py). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools.rs), [Proteus 3](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/invocation.rs).

### ECO2-P01 — Актуальный Proteus уже имеет ConversationView поверх canonical snapshot

В Core pin 3f36a… есть ConversationView schema1 с source harness/version/session/revision, projection=Conversation и полным ConversationSnapshot. Snapshot текущего root читается в checkpoint lock order; tool owner разрешается однозначно по call ID.

**Перенос в Proteus:** Старый readcompat proof использовать как ограниченный reporting-only mapping пример, не как актуальное доказательство отсутствия view. Новый research consumer читает существующие типы и добавляет только предметные evidence locators.

**Граница доказательства:** View исключает заменённую compaction history и uncheckpointed streaming; revision не SSE cursor и не доказательство внешнего состояния. Старый proof pin другой и не был перезапущен.

[Источник 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation/view.rs), [Источник 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation.rs#L16-L70), [Источник 3](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/conversation.rs). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation.rs#L16-L70).

### ECO2-P02 — Настоящий пробел — correction/retraction consumer, не ещё один блоковый selector

Memory-pack append-only remember/substring recall не даёт object-level replace/retract/CAS; evidence-blocks выбирает supplied immutable config revisions, ничего не пишет и provenance_verified=false. Новый json_contracts producer уже умеет strict full-read/hash/actual assertions, но не quote spans.

**Перенос в Proteus:** Пара реальных потребителей: evidence.verify_spans (точные bytes/hash/span, не truth) и memory.correct_fact (прочитать prior revision→проверить source quote→показать proposal→host-authorized CAS update→прочитать новый current view). Начать с single-owner local store и deterministic fixtures.

**Граница доказательства:** В этом исследовательском раунде только design. Ни новый модуль, ни quote-verification tests, ни durable store implementation не созданы. Существующий producer нельзя объявлять криптографически аутентифицированным raw filesystem snapshot.

[Источник 1](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/lib.rs#L84-L158), [Источник 2](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/context_provider/memory-pack/src/tools.rs), [Источник 3](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks/src/lib.rs#L31-L151), [Источник 4](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29d31fb36397008b7677cd5df4943031e24e8fdf/examples/letta-evidence-blocks/src/lib.rs#L189-L248). [Proteus 1](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/conversation.rs#L16-L70), [Proteus 2](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs).

## 4. Реальный недостающий producer: `evidence.verify_spans`

### Сценарий без ложного «источник доказывает истину»

Пользователь просит обновить справку или долговременный факт по новому документу. Research workflow предлагает фразу и точную цитату; verifier независимо читает разрешённый источник через host tool, проверяет bytes, а consumer показывает:

- цитата действительно присутствует в наблюдённой ревизии;
- утверждение модели — отдельная интерпретация, semantic entailment **не проверялось**;
- противоречащая старая цитата может быть показана рядом, а не молча удалена;
- изменение памяти пока только proposal, не permission grant.

Это уже реальная вычислимая цепочка, а не граф из self-reported source IDs.

### Узкий первый интерфейс

Owner config фиксирует allowlist `source_id → relative path`, trusted reader convention, per-file/total/output budgets. Модель не может поменять allowlist, expected policy или объявить результат проверки.

Запрос каждого quote содержит:

```text
source_id
expected_content_sha256
start_byte, end_byte          # half-open UTF-8 byte range
quote
```

Действительная работа:

1. Host-bound `read_file` по configured path; запрет partial/redacted/unknown conventions согласно inspected strict reader helper.
2. Проверка call ID, success/error, exact resolved path, truncation flags, full line counts и byte limits.
3. SHA-256 **ровно возвращённых UTF-8 bytes** без нормализации пробелов/CRLF.
4. Проверка ожидаемого digest, диапазона, границ UTF-8 и буквального равенства `bytes[start:end]` переданной цитате.
5. Результат `exact_match` или конкретный refusal: stale digest, out-of-bounds, split UTF-8, quote mismatch, denied/partial read, cancellation.
6. Audit correlation с verifier/read call IDs и host attribution; consumer принимает только фактически полученный tool result, а не присланный моделью объект с таким же видом.

**Что переиспользовать:** существующий json-contracts producer уже содержит строгий full-read reader и digest путь. Не надо создавать второй несовместимый «универсальный reader». Выделение общего helper имеет смысл только если этот второй consumer действительно реализуется и интерфейс остаётся pinned.

**Что не обещать:** hash не удостоверяет источник и не доказывает истинность; matched quote не доказывает, что вывод автора/модели логически следует из неё. AfterTool или trusted reader способны изменить bytes, поэтому текущая гарантия — совпадение с наблюдёнными trusted-callback bytes, не криптографическое подтверждение диска. Между чтением и применением память/источник могут измениться.

**Не выдавать в общий completion gate как «код проверен».** Нужен отдельный namespaced результат `semantic_entailment: not_evaluated` и consumer, проверяющий соответствие конкретному proposal. Существующий Hermes v1 gate не проверяет сам expected suite/hash/coverage; один красивый digest в check ID не добавит ему этой семантики.

### Вторая ступень: цитаты из conversation

Использовать `host.conversation.snapshot` и `ConversationView`, а не загружать чужой журнал в executable history. Locator: source/session/revision/message_id/part_id/`Text`/UTF-8 byte range. Исключить reasoning и mutable runtime projections по умолчанию; unavailable compacted message даёт incomplete, не пустой successful match.

Старый readcompat может помочь read-only отображением поддерживаемых native sources, но импортированный System не превращается в нашу инструкцию, а source-default success не превращается в authenticated effect receipt. Необходимость attachment resolver доказывается конкретным источником, не вводится на всякий случай.

## 5. Реальный consumer: `memory.correct_fact`, а не ещё один selector

### End-to-end use case

Старая память: «Команда проводит обзор по четвергам». Пользователь присылает проверяемое изменение: «Теперь обзор по вторникам». Дополнительный агент ещё работает со старой ревизией.

1. Прочитать текущий факт `fact_id`, его revision и прежний источник.
2. Проверить новую цитату через `evidence.verify_spans`; модель может предложить формулировку, но не самостоятельно повысить доверие.
3. Вернуть proposal с old/new/diff/source locator и точным expected revision. Если основания конфликтуют — явный conflict, не автоматическое «объединить».
4. Получить необходимое для записи разрешение через обычную host policy. «Источник говорит, что можно менять память» не является таким разрешением.
5. Применить bounded update/retract к **module-owned single-owner store** с атомарной проверкой expected revision. Повтор operation key с тем же request digest возвращает уже записанный outcome; с другим payload отклоняется.
6. Прочитать новую current view и вернуть applied revision. Context provider на следующем чтении выдаёт текущую запись с provenance/freshness, сохраняя предупреждение о характере данных.
7. Устаревшая параллельная попытка получает conflict; она не перезаписывает новую запись. Lost ACK требует lookup той же operation identity, а не нового update.
8. Retraction suppresses future recall, но не обещает удалить старые prompts/journals/exports/backups. Это отдельная retention/privacy задача.

### Минимум, который действительно нужен

- Существующий `tool/v6` для read/propose/apply/retract и `context_provider/v4` для автоматического read-only projection.
- Owner-configured namespace/store location и правила изменения; principal не выбирается текстом модели.
- Module-local typed record: identity, revision, value/tombstone, source locator/digest, update reason, prior revision, operation key/request digest.
- Реальный backend, обеспечивающий CAS и recovery. `read_file` затем `write_file` **не** атомарный CAS; один process Mutex **не** cross-process гарантия.
- Для file-backed реализации: поддерживаемая lock/atomic publication/fsync семантика, immutable committed revisions + валидируемый current pointer, bounded history/retention policy. Для DB — конкретная transaction primitive. Не нужно обещать одновременно все backends.
- Writes проходят обычную host tool authority/recording. Provider ничего не мутирует и не вызывает другой модуль напрямую.
- Отдельные результаты applied, rejected_conflict, pending, unknown; projection refresh не отменяет записанный факт.
- Data provenance и semantic confidence не равны execution authority.

Это **предложение**, не готовая реализация и не новые Core guarantees. На первом этапе достаточно одного single-owner local backend, не distributed memory service, Git синхронизации или universal ACL. Нельзя создавать surrogate host authority из module ID/языка.

### Приёмка реальной реализации

Нужны authored deterministic проверки: stale writer; duplicate operation; duplicate key/different payload; crash между prepared и committed publication; ACK lost после commit; cancellation до/после записи; provider читает старую либо новую целую ревизию; tombstone не проигрывает lexical ranking; invalid quote/hash/span; bounded output; hostile source text не меняет allowlist; ambiguous foreign call IDs не получают invented status.

Реальный SDK/host smoke должен показать host nested read/policy/attribution и canonical result binding. Самостоятельный state-machine unit test не считается Core reproducer; fake model не доказывает качество memory extraction. Ничего из этого в этом исследовательском раунде ещё не запускалось.

## 6. Что переносить выборочно

**Переносить:** progressive disclosure, separate commit/projection outcomes, explicit attachment membership, owner-token transitions, completed-result filtering on resume, accepted-vs-stored distinction, bounded validation повторно после merge, content availability в evidence.

**Не переносить буквально:** API V1 как текущий Letta; arbitrary memory в system policy; Git hooks как доверенный verifier; process-local watermark как durability; snapshot как authority receipt; background success как stored; mutable shared dictionary как transaction; source graph как truth proof; ещё один общий Conversation DTO.

У Strands особая полезная отрицательная проверка: `flush()` может завершиться после best-effort extraction и всё же не быть положительной квитанцией всех memory writes. У Letta — recompile failure не означает, что memory update не состоялся. Обе границы естественно ложатся на существующее разделение raw effect и projected response в Proteus.

## 7. Точное ограничение и следующая полезная работа

Не покрыты current Letta Cloud backend/ACL, full local-store crash recovery, полная конкурентная сериализация prompt compilation, все Strands storage backends, Graph/Swarm scheduling и background tool runtime. Source-reviewed здесь значит чтение перечисленных ranges, не аудит каждого файла целиком. Неподтверждённые вопросы не представлены здесь как bugs.

Следующий практический выбор — **второй настоящий consumer** строгого reader: quote/span verification либо scoped memory correction store. До реализации полезен узкий reference contract review по CAS/idempotency и host result binding, а не написание очередного DTO/example без действий.

Следующее самостоятельное source-направление, если нужна ширина: OpenHands **SDK computer/action-event** и среда исполнения с recovery, либо агент для retrieval/research с persisted citations. Не возвращаться просто к очередному coding loop. First batch остаётся неизменным.

### Пакет

`public-ledger.json` — 19 наблюдений; `source-manifest.json` — 46 hashes/URLs; `coverage.json` — ranges/exclusions и comparison evidence; `hash-verification.txt` — проверка исходных артефактов; `validation.json` — их историческая проверка согласованности. Полные source snapshots в этот пакет не включены.
