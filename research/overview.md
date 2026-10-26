# Расширяемость и надёжность Proteus

Срез исследования — **25 октября 2026 года**. Цель — найти полезные механизмы других агентов, конкретные дефекты и небольшие оптимизации, а затем показать переносимые идеи в Rust без ослабления Proteus.

**Главный вывод:** максимальная гибкость совместима с надёжностью, если свободно менять policy, данные и adapters, но сохранять у host владение идентичностью действий, полномочиями, журналом, завершением операций и ресурсами. Это не означает «заморозить Core»: новые типизированные контракты нужны там, где появился настоящий consumer и существующий интерфейс не выражает требуемую гарантию. Один универсальный plugin runtime для всех задач не нужен.

В [машинном каталоге](catalog.json) собраны **90 недублированных публичных записей** и **44 группы отвергнутых гипотез**: не только приоритетные баги, но и малые оптимизации, существующие возможности, осознанные ограничения, reference patterns и предложения. Проверка безопасности ведётся отдельно; её чувствительные детали здесь не публикуются.

## Что проверено

Исследованы выбранные producer/consumer paths на закреплённых commits, а также официальная документация. **Статически найденный механизм — не выполненный reproducer и не подтверждённый production incident.** Для условных последствий указаны ограничения и следующая минимальная проверка.

Ведомость чтения пяти публичных направлений после дедупликации по repository + commit + path содержит **160 полностью прочитанных файлов и 135 дополнительных частично прочитанных**. Здесь учитываются также документация, manifests и исходники тестов. Это не процент покрытия репозиториев и не утверждение, что все свойства этих файлов проверены. Полный clone сам по себе не считается чтением.

**Upstream tests, benchmarks и live model requests — NOT RUN.** Отдельно выполнены тесты трёх новых Rust-примеров; их результаты ниже. Численных обещаний ускорения нет.

## Три практических Rust примера

Все примеры используют официальный Proteus SDK на commit `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`, Rust **1.95.0** и отдельные Cargo.lock. Это самостоятельные модули, а не изменения Core.

| Пример | Контракт и назначение | Выполненная проверка |
|---|---|---|
| [hermes-verify-evidence](../examples/hermes-verify-evidence) | `hook/v6`: оценка verification receipts и ограниченное продолжение turn | **23 policy + 1 real-executable wire test PASS** |
| [pi-ready-steps](../examples/pi-ready-steps) | `tool/v6`: детерминированные рекомендации готовых узлов DAG | **11 unit tests PASS**; дополнительно **14 direct wire checks PASS** и **официальный SDK conformance broker smoke PASS** |
| [letta-evidence-blocks](../examples/letta-evidence-blocks) | `context_provider/v4`: отбор supplied evidence с revision, tombstones, scope и бюджетом | **14 unit + 1 real-executable wire test PASS** |

Итого **50 Rust tests, 0 failed, 0 ignored**. Дополнительные Pi wire checks и broker smoke не прибавлены к этому числу. Также PASS: `cargo fmt --check`, locked builds, сравнение source digests до/после; **12 regression tests** воспроизводимого Python runner. Отдельно подтверждён официальный SDK broker handshake Hermes и Letta. [Результат пакетной проверки](../validation/results.json).

Полная загрузка Core host/config assembly, production deployment, in-flight cancellation/concurrency и release profile **не проверены**. End-to-end интеграция с внешними системами не установлена.

**Hermes — policy, не готовая система проверки тестов.** Пример анализирует receipts из retained canonical history. Для реальной эксплуатации нужен отдельный доверенный producer, который отличает настоящую проверку от произвольного exit 0, пропущенных/нулевых тестов и текстового «всё прошло». Синтетические fixtures этого не заменяют; provenance enum не является подписью. Внешние изменения и удалённая compaction история могут быть невидимы.

**Pi — advisory graph, не scheduler.** Модуль не выполняет узлы, не владеет их жизненным циклом и не обещает durable replay. Переданные статусы — входные данные, а не доказательство совершённых действий. Admission и реальное выполнение остаются у host.

**Letta — owner-configured evidence, не подключение к Letta.** Нет сетевого клиента, authenticated memory service или записи во внешнюю память. Scope — правило отбора, не удостоверение пользователя; supplied revisions не доказывают актуальность источника. Бюджет необходимо понимать в рамках выбранного renderer, а не как универсальный точный token budget всех моделей.

## Что брать у других систем

| Направление | Реально исследованный материал | Полезный перенос и граница |
|---|---|---|
| Coding agents | Pi, Codex, OpenCode, Hermes, DeepSeek — выбранные исходники на точных pins | Replay intent, cancellation arbitration, retry budgets, hooks, context pipeline и наблюдаемость; не переносить чужие гарантии по названию API |
| Модульная композиция | Cordis в составе DeepSeek; Pi staging; OpenCode finalizers | Validate/stage/publish и scoped disposal; DI не заменяет quiescence зависимостей |
| Durable workflows | LangGraph — выбранные loop/checkpoint paths; Pydantic AI — selected backend/registration methods | Семантическая операция отдельно от backend binding; saver и worker reconstruction требуют собственных проверок |
| Durable service steps | Restate — официальная документация | Journaled step boundaries; внешние effects всё равно требуют idempotency/reconciliation |
| Долговременная память | Letta — официальная документация; Proteus stores — исходники | Stable IDs, revisions, attach/detach, forgetting; last-write-wins не является conflict-free merge |
| Multi-agent и human-in-loop | DeepSeek/Hermes — source/docs; OpenClaw, ADK, AutoGen — преимущественно docs | Capability-aware child backends, отдельное наблюдение и управление, durable pending decisions |
| UI и interoperability | MCP, Agent Skills, Agent Plugins, ACP, A2A; AG-UI, A2UI, MCP Apps | Отдельные adapters по назначению: tools, data packages, editor sessions, remote tasks и UI projections |
| Research и browser agents | Требования к разнородным workers и evidence; OpenHands использован только для архитектурной навигации | В этом проходе **нет** end-to-end проверки browser control, качества исследований и retrieval provenance |

Документированные ограничения нужно читать буквально: ADK описывает at-least-once повтор незавершённого tool, а AutoGen — ограничения сохранения команды при блокирующем mid-run UserProxyAgent. Это не повод считать эти системы «ненадёжными вообще» и не доказательство дефекта Proteus. Это границы конкретных механизмов. [ADK resume](https://adk.dev/runtime/resume/), [AutoGen human-in-loop](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/human-in-the-loop.html).

## Что в Proteus уже есть

Сохранять и развивать стоит существующие execution snapshots, host-bound operations, raw effect facts, canonical journal, offline replay, context preparation/compaction, memory providers, catalog cache, backpressure и priority control lanes. Уже реализованы skills, AGENTS.md context, Agent Plugins importer, ACP v1, process contracts и ограниченный Claude command-hook adapter. Предлагать их «добавить с нуля» было бы ошибкой. [Execution snapshot](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/execution.rs#L1-L150), [replay](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/workflow_replay/mod.rs), [plugins importer](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/agent_plugins/mod.rs#L22-L176).

При этом checkpoint истории не равен сохранению произвольного program continuation, plan `completed` не доказывает внешний эффект, а shell session не является durable background job. Local journal не создаёт атомарную транзакцию с внешним API.

## Наиболее практичные исправления

### Сначала точность представлений и восстановления

**CM-02/03 — reasoning replay.** Anthropic redacted blocks выпадают из canonical roundtrip; opaque reasoning payload не несёт достаточного provider/API/model discriminator. Нужны небольшие representation и adapter compatibility изменения, а не новый формат всего чата. Original history остаётся неизменной, provider получает допустимую projection. Первая проверка — offline decode→canonical→encode и provider-switch matrix. [Anthropic decoder](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/model/model-pack/src/adapters/anthropic/response.rs#L30-L85), [OpenAI reasoning decoder](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/model/model-pack/src/adapters/openai/response/item.rs#L49-L71).

**CM-05/06/07/08 — request semantics.** Различать default/on/off, считать холодный instructions/tools/image overhead, сохранять typed provider failures и явно обозначать новый generation attempt после stream failure. Доказан повтор model request, но не повтор выполнения tools; стоимость и UI artifact не измерены. [Reasoning mapping](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/model/model-pack/src/adapters/anthropic/request.rs#L72-L103), [preflight](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/workflow/coding-workflow/src/host.rs#L271-L291), [Anthropic transport](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/model/model-pack/src/adapters/anthropic.rs#L179-L258).

**EXT-01/03/04/06 — малые interoperability fixes.** Коллизии нормализованных MCP имён должны оставаться внутри server/generation failure domain; reconnect должен учитывать обновление каталога; output schema можно сохранить в уже существующем ToolSurface; отключённый malformed skill не должен непреднамеренно срывать discovery остальных. Следующий шаг — synthetic server и skill fixtures, не переписывание plugin системы. [MCP discovery](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/tools/mcp/discovery.rs#L15-L94), [client](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/tools/mcp/client.rs#L58-L239), [skill discovery](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/tool/skill-pack/src/discovery.rs#L43-L324).

**CO-01 — неизвестный ACK.** Если host принял сообщение, а HTTP ответ потерян, клиенту нужно состояние unknown и reconciliation по сохранённой operation identity, а не категорическое «Не отправлено» с новой identity при повторе. Это отдельный условный desktop сценарий, не старый исправленный partial-ACK bug. [Desktop send](https://github.com/Proteus-harness/Proteus-desktop/blob/1c1eba386849e3123e14580273487b5314287eb6/src/ui/chat/actions.rs#L39-L88), [host admission](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/app_server/http/commands.rs#L187-L223).

### Затем lifecycle и fault gates

**CORE-WRITER-LIFETIME.** Static strong-Arc registry сохраняет writer state и lock после удаления внешних handles. Это значимо для long-lived сервера и передачи сессии, но может быть сознательной process-lifetime policy CLI. Проверять нужно last-handle release одновременно с in-flight transaction protection; нельзя просто снимать lock раньше worker. [Registry](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/session_store.rs#L284-L294), [writer transaction](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/session_store/writer.rs#L15-L30).

**CORE-DIR-DURABILITY и RUNTIME-LATE-RESULT.** Для поддерживаемых файловых систем проверить persistence имени blob после rename; отдельно — сохранение наблюдённого late outcome внутри grace после cancel. Последствия условны: power loss не равен обычному process crash, а cancel не доказывает отсутствие действия. [Blob install](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/session_journal/storage.rs#L292-L334), [cancel settlement](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/invocation.rs#L79-L122).

### Оптимизировать повторную работу без смены гарантий

**PQ-01/02 — первые кандидаты на профиль.** Append клонирует растущий validation state; один набор record IDs даёт суммарно Ω(N²) копирований за N записей. Async turn повторно синхронно загружает full projection. Это сильные статические основания измерить allocations, bytes read и stage latency, но ещё не обещание конкретного ускорения. [Append](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/session_journal/storage/append.rs#L69-L86), [turn](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/runtime/turn.rs#L223-L255).

Следом — повторные cold recovery passes, cache capacity cliffs, aggregate bytes snapshot/desktop queues, дополнительные IPC сериализации, search parse/buffers и ранние skill discovery bounds. Малые JSON roundtrips и fixture caching тоже сохранены в каталоге, но не объявлены важнее измеренных hotspots. **Fsync, validation и durability barriers не отключать ради красивого результата.**

Качество измерять отдельно: более быстрый FTS backend может вернуть другой набор фактов, а успешный replay — не доказательство правильного решения задачи. Stable prompt prefix, свежий retrieval и speculative summary — tradeoffs с расходами и freshness, не бесплатные ускорения.

## Где расширять контракты

| Поверхность | Что может выбирать модуль | Что остаётся у host |
|---|---|---|
| Planning | DAG strategy, reviewer, fail-fast/all-settled | Реальное admission, identity и результат эффекта |
| Model/context | Provider profile, retrieval, pruning, summary policy | Совместимость wire/replay, исходный snapshot, validation и commit |
| Memory | Ranking, retention, CRUD policy | Разрешённые read/write effects, revision conflict и lineage |
| Retry/workflow | Backoff, classification, backend | Бюджет, stable operation key, unknown outcome и reconciliation |
| Hot reload | Состав exports, новая implementation generation | Stage/publish, coherent admitted snapshot, quiescence и disposal |
| UI/remote | Renderer, transport, worker backend | Scope/identity, capability checks, command admission и terminal settlement |

Практический порядок: **pure/advisory module → workflow на существующих host operations → новый typed contract при доказанной необходимости → backend-specific implementation**. Удалённый A2A task, локальный hook, SKILL.md и UI plugin не обязаны делить один state object.

Хорошие кандидаты на следующий уровень — durable operation с stable identity/version и реконструкцией worker dependencies; conversation fork от settled boundary; child backend с честной capability matrix; отдельные MCP resource list/read operations. Не нужно заранее обещать arbitrary closure continuation, полный MCP tasks runtime или бесшовный resume любого внешнего агента. [Pydantic backend](https://github.com/pydantic/pydantic-ai/blob/ead5e549b69a1d2308c771f6140db666f08413bb/pydantic_ai_slim/pydantic_ai/durable_exec/_operation_backend.py#L125-L197), [registration constraints](https://github.com/pydantic/pydantic-ai/blob/ead5e549b69a1d2308c771f6140db666f08413bb/pydantic_ai_slim/pydantic_ai/durable_exec/_base.py#L784-L856), [MCP resources prior art](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/mcp/mcp-resources/src/tools.ts#L31-L64).

## Следующая проверяемая работа

1. **Закрыть оставшуюся integration примеров:** воспроизводимый runner и перечисленные wire checks уже проходят; далее Core-host/config assembly, in-flight cancellation/concurrency и deployment fixtures. Для Hermes отдельно реализовать trustworthy receipt producer.
2. **Offline correctness fixtures:** reasoning roundtrip и provider switch; request budgets/error classification; MCP catalog/era/reconnect; skill discovery; desktop unknown ACK.
3. **Lifecycle/fault fixtures:** last-owner release, late result, crash/power-loss boundaries и unknown-effect reconciliation. Результат нужен в виде failing-before/passing-after regression, а не только архитектурного текста.
4. **Performance baseline:** synthetic model/workloads, fixed source/lock/toolchain, cold и warm отдельно; CPU, allocations, peak RSS, stage timings, failures. Принимать ускорение только при сохранении correctness gates.
5. **Новые consumers:** сначала readonly one-shot research worker, bounded child inspector и evidence lifecycle; затем при необходимости remote/durable execution. Browser automation и качество исследований требуют собственного следующего прохода.

Этот план — **не список уже выполненных tests**. Публичный каталог сохраняет исходные IDs, exact source links, evidence level, caveats, следующий минимальный эксперимент и маркировку NOT RUN для исследовательских находок.

## Зафиксированные версии

Основные pins: Proteus Core `3f36a003…`, modules `04114bbe…`, desktop `1c1eba38…`; Codex `970111f6…`, Pi `d5b3de22…`, OpenCode `28907e89…`, Hermes `80846849…`, DeepSeek `22ddee37…`, LangGraph `a25bfafe…`, Pydantic AI `ead5e549…`. Полные 40-символьные revisions и ссылки, включая protocol specifications, находятся в `source_pins` [каталога](catalog.json).

Mutable documentation links проверялись на дату среза, но не выдаются за immutable source pins. Desktop extensions имеют проверенный repository ref, не полный source audit. Покрытие остаётся выборочным; «изучены все агенты и любые мелочи» этим материалом не заявляется.
