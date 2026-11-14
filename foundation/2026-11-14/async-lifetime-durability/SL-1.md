# SL-1: workflow stream pump теряет process invocation lineage

**P2, условный source-only finding.** При объединении workflow и model exports в одном exact broker запуск model stream проходит как новый root вместо nested invocation. При насыщении root admission это оставляет model-вызовы в очереди, хотя резерв nested capacity свободен. Это вывод из трассировки исходников, **не выполненная runtime-репродукция**.

## База и уровень evidence

Проверена восстановленная база Core `89997df995df7c39b713e16aba216ecb19c8f497` с delivery [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89), результирующее дерево `00a3c04a70d7927d1688ea155142025f596a2874`. Перечисленные ниже production-файлы, архитектурный документ и example config этими patches не изменены, поэтому ссылки закреплены на upstream commit. Более поздний upstream требует повторной проверки.

Фактически выполнены чтение и сопоставление source chains, проверка dependency source для закреплённого Tokio, дедупликация опубликованного корпуса и независимая повторная трассировка. Rust toolchain отсутствовал. Rust tests/build, запуск worker, нагрузочный эксперимент и измерения времени **не выполнялись**. Исходники не изменены. Наличие этого документа не означает исправление runtime.

## Нарушаемый контракт

В [process-module-architecture.md:675–684](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/architecture/process-module-architecture.md#L675-L684) host-routed reentry в другой export того же exact broker должен получать parent, сохранять root и использовать ограниченную nested lineage. Вызовы другого component остаются roots. Объединение callback-связанных exports явно разрешено этим же документом:700–701.

Это допустимая topology, а не гипотеза об обязательном stock profile: [one-component example](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/configs/proteus.one-component.example.toml#L24-L29) размещает workflow в `reference-agent`, а [строки 80–83](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/configs/proteus.one-component.example.toml#L80-L83) добавляют в тот же component model.fake. Сам example является test aggregate, не штатной поставкой. Факт воспроизведения на нём не заявляется.

## Проверенная причинная цепочка

1. [`InvocationScopedDispatcher`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/invocation_scope.rs#L8-L55) помещает broker-owned `InvocationRef` в Tokio task-local `ACTIVE_INVOCATION` только на время callback future. `current_parent` возвращает parent лишь для того же `Arc<ComponentBroker>`; отсутствие task-local даёт `None`. Поиск по crates не обнаружил второго места, устанавливающего этот scope.
2. [`WorkflowHostRuntime::start_model_stream`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/workflow_host.rs#L109-L122) вызывает `ModelStreams::start` в callback. Но [`model_stream.rs:63–100`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/workflow_host/model_stream.rs#L63-L100) выполняет `ctx.require_model()?.stream(request).await` уже внутри `tokio::spawn`. В новую task явно переносится только `ModelCallOrigin::Direct`.
3. [`with_model_call_origin`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/model_call_scope.rs#L5-L20) устанавливает лишь `MODEL_CALL_ORIGIN`. Оно не восстанавливает `ACTIVE_INVOCATION`. Клонирование `ExecutionContext` также не переносит этот process-adapter task-local.
4. В цепочке [`BoundModel::stream → stream_with_deadline`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model.rs#L298-L344) → `ModelService::start_prepared` → [`ProcessModel::stream`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/model.rs#L250-L269) нет восстановления process lineage. `ProcessModel` вызывает `client.start` внутри spawned task.
5. [`ProcessExportClient::start`:247–270](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/client.rs#L247-L270) выбирает `start_nested_invocation` только при `Some(parent)`. Для `None` вызывается root API `start_invocation_with_dispatcher`. Это не только потеря диагностического поля: выбор меняет admission path.
6. Broker по умолчанию имеет [16 active roots, 32 total и reserve 16 nested](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-module-protocol/src/v3/config.rs#L52-L61). [`runtime.rs:433–444`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-module-protocol/src/v3/runtime.rs#L431-L444) ставит новый root в `queued_roots`, когда active roots уже 16. Незанятый nested reserve не позволяет активировать такой root. Настоящий nested вызов пошёл бы по [отдельной ветке admission:249–293](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-module-protocol/src/v3/runtime.rs#L249-L293).

### Почему отсутствие scope не зависит от удачного scheduling

В [Cargo.lock:2094–2097](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/Cargo.lock#L2094-L2097) закреплён Tokio 1.52.2. В его первичном исходнике [`TaskLocalFuture::poll`](https://github.com/tokio-rs/tokio/blob/tokio-1.52.2/tokio/src/task/task_local.rs#L393-L416) устанавливает local только вокруг poll обёрнутого future; [`scope_inner` и guard](https://github.com/tokio-rs/tokio/blob/tokio-1.52.2/tokio/src/task/task_local.rs#L179-L219) затем восстанавливают слот. [`spawn`](https://github.com/tokio-rs/tokio/blob/tokio-1.52.2/tokio/src/task/spawn.rs#L15-L25) не делает синхронный poll новой task и допускает другой worker thread. Сам по себе запуск из scoped callback не наследует этот task-local. Здесь вывод сделан из pinned dependency source, а не из предположения о поведении task-local в другом runtime.

## Точные условия и границы последствий

Для отказа admission нужны одновременно:

- workflow и model используют **один exact broker**, а не просто одинаковый executable или module_id. [`ProcessComponentLauncher::connect`:228–240](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/config.rs#L228-L240) кэширует broker по canonical workspace внутри данного launcher;
- все 16 root slots заняты workflow invocations до запуска их model streams;
- эти workflow ждут результаты своих streams и не завершаются по независимой причине;
- model invocation действительно доходит до данного process adapter. Для чистого теста надо исключить посторонние hooks и другие pending invocations, которые изменят admission или упадут раньше.

При этих условиях source chain приводит к ожиданию model roots в очереди до освобождения root capacity, timeout или cancellation. После первого такого события часть остальных вызовов может продвинуться. **Вечный deadlock и обязательный одновременный timeout всех 16 вызовов не заявляются.** Если roots свободны, модель может успешно выполниться, но с root вместо nested lineage. При разных brokers новый root является предусмотренным поведением и не доказывает этот finding.

Inline [`complete_model`:135–152](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/workflow_host.rs#L135-L152) не делает этот spawn и сохраняет callback task scope. Это контроль для локализации дефекта, не универсальная рекомендация выключить streaming.

Отсутствие parent также убирает именно broker-level наследование deadline и дерева, но **не означает отсутствие cancellation вообще**. `ProcessWorkflowAdapter::run` вызывает [close_model_stream:89–101](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/workflow.rs#L89-L101), а [`ActiveStream::drop` и `close`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/workflow_host/model_stream.rs#L128-L135) отменяют pump. ProcessModel имеет `CancelOnDrop`, BoundModel также использует execution cancellation. Permanent leak, privilege escalation, journal corruption и потеря данных не установлены.

## Regression plan, НЕ РЕАЛИЗОВАН И НЕ ЗАПУЩЕН

1. **Минимальный lineage oracle.** Один process fixture экспортирует workflow и model; оба подключены через один launcher и canonical workspace. Workflow вызывает `host.model.stream.start`, затем читает stream. Test model возвращает наблюдённые invocation `root`, `parent`, `depth` как test-owned данные. Ожидаемый контракт: parent равен workflow invocation, root сохранён, depth увеличен на один. Текущее поведение по source chain: parent отсутствует, depth равен нулю. Проверять реальные host-routed operations, не только прямой вызов `ProcessExportClient`.
2. **Детерминированное насыщение.** На default limits запустить 16 workflow roots. Barrier в fixture выпускает их к stream start лишь после регистрации всех 16 активных workflow. Fake model не использует сеть и мог бы сразу вернуть terminal response. Hooks отключены, tools отсутствуют. Test instrumentation должна подтвердить, что все model starts дошли до admission, а не полагаться на случайный sleep. До освобождения root slot фиксировать queued roots и отсутствие model delivery при 16 свободных nested slots. Проверять ожидаемую причинную связь, а не превращать произвольный короткий timeout в доказательство.
3. **Контроли.** Тот же barrier и synchronous `host.model.complete` должны сохранить nested lineage; отдельный прогон с model в другом broker должен остаться root. Один stream при свободной root capacity отделяет identity failure от throughput symptom. Проверить и current-thread, и multi-thread runtime, если используемая integration fixture поддерживает оба.
4. **Settlement.** После observation point выполнить cancellation; проверить завершение stream.next, закрытие pump и отсутствие pending model/workflow invocation после штатного settlement. Повторить успешный следующий turn. Эти проверки необходимы для будущего исправления, но их исход сейчас не утверждается.

Ближайший существующий [callback_reentry test](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/client.rs#L433-L444) проверяет прямые async/blocking вызовы context/provider/policy, а не workflow stream pump. Его прохождение не было бы доказательством корректности данного async hop.

## Направление упрощения, не готовый patch

Предпочтительно сделать перенос invocation lifetime через этот async hop одной явной обязанностью существующей границы, сохранив broker-owned lineage. Не размазывать восстановление по отдельным model implementations и не увеличивать root limit вместо восстановления parent.

Есть два направления для проверяемого design choice: инициировать model invocation в ещё активном callback scope до передачи уже созданного stream в pump, либо явно перенести opaque invocation scope через разрешённую внутреннюю границу. Первый вариант может менять момент ack/error stream.start; второй должен сохранить запрет protocol-specific lineage в Core и не дать модулю подделывать parent. Здесь вариант не выбран и готовность patch не заявляется. Ни новый публичный slot, ни обязательные conversation identity, ни универсальный task framework для этого finding не требуются.

Ожидаемый выигрыш качественный: один источник parent/admission semantics, меньше зависимостей от того, где случайно находится `spawn`. Изменение LOC, latency, RSS и частота production-сбоев не измерены.

## Независимая проверка и дедупликация

Независимая повторная трассировка подтвердила единственное место установки `ACTIVE_INVOCATION`, отсутствие переноса через spawn и отсутствие восстановления в BoundModel → ModelService → ProcessModel; отдельно перепроверены exact-broker predicate, reserved capacity и inline complete control. Review потребовал оставить оговорки про barrier, timeout/cancel и different-broker control. Runtime verification в review также не проводилась.

Проверены 97 MD/TXT reports/README/addenda из [continuous audit index](https://github.com/Qweasd123tg/proteus-modules-dot/blob/main/research/proteus-continuous-audit-2026-11-13/README.md), полный ноябрьский audit DOCX и [PR91](https://github.com/Qweasd123tg/proteus-modules-dot/pull/91). Прямого дубликата в проверенном корпусе не найдено; абсолютная новизна не гарантируется. Ранее описанное удержание canceled queued-root IDs и stale callbacks после cancellation имеют другую причинную цепочку. Кандидаты PR91 относятся к history cache, tool result identity и zero timeout, не к утрате task-local process lineage.

Документ содержит только source analysis и неисполненный план проверки. Исходники, бинарные сборки, credentials и пользовательские данные не включены.
