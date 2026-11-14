# Session-owned shutdown across runtime epochs

## Статус и точная база

Это проверенный по исходникам дизайн и контракт будущих тестов, **не runtime patch**. Production-файлы, wire, contracts и executable не изменены. Rust tests/build/fmt не запускались: в текущем изолированном окружении нет `cargo`/`rustc` и подготовленного Modules reference fixture.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89). Проверенное дерево `00a3c04a70d7927d1688ea155142025f596a2874`. Дизайн применим к этому дереву; изменения upstream после этой базы требуют повторной проверки. Это предложение не применяет патчи к upstream и не исправляет runtime.

Результаты других прототипов и их тестов не используются как доказательство этого дизайна.

## Результат slice и не-цели

После успешного `shutdown()` одной live session:

1. Новая admission закрыта, в том числе через сохранённые old-epoch handles.
2. Все её непосредственно зарегистрированные OS peers завершены и reaped; их stdout reader tasks завершены.
3. Нет retained idle/reserved/leased binding, позволяющего возобновить закрытый peer; mailboxes и history retention инвалидированы.
4. Все принадлежащие session execution/monitor tasks и отслеживаемые publication effects дошли до подтверждённого конца. После успешного результата нет новых runtime/pending/collaboration **producer effects** из этой live generation. Это не обещание пустых transport queues: ранее опубликованные события и производная transport activity могут быть доставлены позже.
5. Другие live sessions продолжают работу. Reopen того же durable `SessionId` создаёт новую live identity и не наследует старые handles, queued completions или history bindings.

Это **не** исправление background routing: нового stdout consumer/dispatcher, forwarding owner для idle peers, bus или descendant registry не добавляется. Не обещается доставка background question после завершения foreground parent. Не исправляются call-ID projection, worktree naming, durable tree recovery или уничтожение всех OS grandchildren. Жёсткое wall-clock SLA shutdown для произвольного sink/OS не заявляется.

`Err` не равен успешному закрытию. После cleanup failure нельзя продолжать NewSession, освобождать live owner или удалять storage под видом успешного settlement.

## Подтверждённые исходниками причины

Пути ниже относительны Core; номера строк относятся к точной базе выше.

| Граница | Фактическое состояние | Последствие |
|---|---|---|
| `src/core/runtime.rs:153`; `runtime/reload.rs:75–77` | SessionState живёт отдельно от сменяемого RuntimeSnapshot | Scope нужно хранить в SessionState, не в одном epoch |
| `src/core/registry.rs:38,123`; `agent_control/mod.rs:48–77` | Registry сохраняет erased `Arc<dyn AgentControl>`, typed lifecycle facade теряется | Одного поиска current registry недостаточно для old epochs |
| `agent_control/process/pool.rs:86,170,192,248` | Resume/reuse привязаны к durable SessionId; active lease вынесен из pool | Закрытие только idle pool не охватывает active peer и live reopen |
| `agent_control/process/mod.rs:572–635` | Prepare/reserve выполняются до await `SubagentStarted`; detached task появляется позже | Нужна регистрация lifetime до первой reservation/await |
| `agent_control/pending.rs:99,189` | Detached join monitor публикует PendingOutcome | Ожидание только execution future не является publication barrier |
| `agent_control/collaboration/mod.rs:361–374` | Второй detached monitor выполняет `wait_agent → complete` | PendingOutcome barrier ещё не закрывает collaboration publication |
| `agent_control/collaboration/control.rs:33,116`; `collaboration/mod.rs:32` | Static shared state/history lookup используют только SessionId | Новая live session с тем же ID может увидеть старого owner |
| `agent_control/process/child.rs:238–243`; `process/output.rs:110` | Child владеет OS process; kill error игнорируется; reader Drop только abort | Нет подтверждения reap + reader completion для retained/active объекта |
| `app_server/control_plane.rs:69`; `app_server/runs.rs:311` | Shutdown ждёт root runs, возвращает `()` | Отдельные peer owners и ошибки cleanup не входят в ответ |
| `app_server/stdio.rs:90,355`; `http/lifecycle.rs:133` | После shutdown продолжаются replacement/deletion; stdio отвечает success | Нужна сквозная ошибка без смены wire shape |
| `app_server/http/state.rs:188–208` | Detached watcher получает queued Shutdown и публикует activity | Producer quiescence не равна опустошению transport queues |
| `app_server/http/commands.rs:321`; `http/lifecycle.rs` | Aggregate snapshot может пересечься с new/resume/remember_server | Полный host shutdown требует отдельного admission fence |
| `src/core/event_store.rs:31`; `session_store/writer.rs:115` | Event sink делает async filesystem I/O; journal transaction передаёт работу spawn_blocking | Abort/drop caller future сам по себе не доказывает отсутствие позднего I/O |

Все `src/...` в таблице относятся `crates/proteus-core/`, кроме отдельно упомянутых ниже contracts.

## Выбранная модель владения

### 1. Live scope, а не новый durable ID

Добавить приватный `AgentSessionScope`, создаваемый ровно один раз для нового live `SessionState`. Он содержит stop/admission state, tracked lifecycle owners, cached shutdown outcome и session-owned collaboration state. Его identity основана на владении одним `Arc`, не на `SessionId`, роли, PID, thread ID или epoch number. Clone scope сохраняет identity, reopening durable session создаёт другой scope. Не сериализовать scope и не менять существующие ID в журналах/stdio.

Все initial/reloaded snapshots одной live session привязываются к этому scope до публикации. Registry должен сохранять typed `AgentControlRuntime`, позволяющий получить **согласованную пару** scoped service и scoped tool facade. `tools_for_model` не должен возвращать unbound/global collaboration tools. Исторические snapshots остаются привязаны к прежнему scope и закрываются им же. Public/custom service injection и standalone consumers нужно инвентаризировать и мигрировать вместе, не подменять неизвестную реализацию глобальным lookup.

Предпочтительная внутренняя сборка: скопировать tool registry, сохранив non-agent-control entries через существующий `register_from`, затем зарегистрировать session-bound facade с её scope-owned collaboration control; service в workflow context получает тот же bound runtime. Не менять wire и не добавлять lifecycle-поле в сериализуемые DTO. Публичный Rust API может потребовать согласованной адаптации consumers; обещание «один файл без API изменений» здесь неверно.

Сборка связки должна структурно запрещать смешивание old facade и unrelated/new scoped service. Проверки только `host.session_id()` недостаточно при same-ID reopen. Это отдельный integration gate, а не допущение тестовой модели.

### 2. Линеаризация admission/close

Под коротким lifecycle mutex `begin_operation()` либо выдаёт guard, либо отклоняет Closing/Failed/Closed. Guard приобретается **до** prepare/reserve/emit/OS spawn и покрывает rollback при любом раннем выходе. Close атомарно переводит Open → Closing и получает всех ранее зарегистрированных owners. Нельзя «сначала проверить open, потом spawn, потом зарегистрировать».

OS spawn выполняется только внутри already-admitted lifecycle owner. Если closing победил до самого OS spawn, spawn отклоняется. Если spawn уже произошёл, его supervisor зарегистрирован в том же scope до отпускания admission fence и close его обязательно ждёт. Не держать lifecycle/pool mutex через await; установить единый lock ordering и тестировать rollback.

После успешного close регистрация запрещена навсегда. Reload во время/после Closing не публикует новую доступную admission; failed binding/reload не меняет действующую session. Не выполнять новые fallible lifecycle-операции после persisted config commit: подготовить binding и допуск к publication до commit, сохранить текущую transactional ordering reload.

### 3. OS-only supervisor и отдельный reader completion

Supervisor единолично владеет `tokio::process::Child`; handle в ChildProcess содержит stop channel, observed exit/cleanup result и lifecycle identity. Supervisor **не читает protocol frames и не форвардит events**. Единственным читателем stdout остаётся существующий bounded reader. Supervisor владеет/ожидает его JoinHandle, а turn-логика сохраняет единственное владение data receiver.

У supervisor различаются natural exit и requested stop:

- **Natural exit:** сохранить exit status, не превращать его в reader failure и не прерывать reader до обработки уже записанных данных. Buffered valid terminal response должен дойти до прежнего consumer, затем normal EOF. OS-exited peer уже не reusable. Если stdout удерживает descendant, reader может продолжать ждать до explicit stop; заявлять successful resource cleanup до его завершения нельзя.
- **Explicit session stop/drop:** закрыть writes, запросить kill непосредственного child, инициировать stop reader независимо от kill/reap результата и дождаться обоих cleanup completions. Kill/wait error не пропускает reader stop/join; reader error не отменяет попытку reap. Обе причины агрегируются, а незавершённый resource owner остаётся retained/quarantined. Ожидание EOF недостаточно из-за унаследованного stdout. Expected cancellation reader, инициированная самим supervisor, отличается от panic/unexpected abort.
- **Kill race с natural exit:** только подтверждённый `wait` позволяет классифицировать документированный already-exited случай как завершённый cleanup. Остальные kill/wait/join ошибки не игнорируются. Nonzero exit сам по себе не равен ошибке reap; protocol outcome и lifecycle result различаются.

Drop ChildProcess отправляет stop, но не abort supervisor. Live scope держит supervisor до результата; исчезновение последнего consumer не оставляет бесконтрольный OS Child. Cleanup не передаётся future первого shutdown waiter.

`send/setup` и ожидания human-response должны получать session stop независимо от stdout EOF. `next_output` на natural exit не должен потерять queued terminal из-за biased health branch. PR87 target/ACK/full-frame/ambiguous-delivery/cancel-grace правила сохраняются для обычного user cancel/role timeout. Session shutdown не пытается дописать Cancel в partial JSONL frame.

### 4. Pool, reservation и detached execution

Pool reuse/resume сравнивают live scope identity дополнительно к существующим role/cwd checks. Release/rollback повторно проверяют Closing, а не доверяют ранее вычисленному `alive`. Closing peer нельзя вернуть в idle/resumable. History token экспирируется, mailbox закрывается, permit освобождается.

Нужен RAII owner для leased bookkeeping, а не только имеющийся SpawnReservation. Его drop снимает `leased`/resume binding, инвалидирует history и инициирует supervised cleanup. Он не выполняет async wait под pool mutex. Guard awaiting-role-permit владеет resume reservation до передачи; stalled `SubagentStarted` также покрыт guard.

PendingChildren monitor зарегистрирован до transfer detached execution. Lifetime guard освобождается после PendingOutcome publication, не до неё. Collaboration monitor имеет свой заранее зарегистрированный owner и заканчивается после `control.complete`; обе публикации входят в один close barrier. Незавершённая attach/monitor registration должна либо целиком откатиться, либо уже принадлежать scope.

### 5. Collaboration без static SessionId ownership

Убрать `CollaborationControl::shared()` как production ownership locator. Один control принадлежит live scope и передаётся всем его epoch tool facades; history notifier замыкается на тот же control. Это не новый registry, а перенос владельца существующих bounded agents/completions. Durable SessionId остаётся attribution и проверкой корректной сборки, но не ключом доступа к live state.

Все spawn/list/wait/send/followup/interrupt/history-bind и LaunchReservation rollback используют bound control. После closing внешние новые действия отклоняются; shutdown coordinator сохраняет право выполнять уже зарегистрированное settlement. Old completion/history-bind не могут создать/изменить запись в новом scope с тем же `/root/name`, generation и SessionId. Старый wait не блокирует переоткрытую session.

Удаление глобального `MAX_SESSIONS=64` lookup **меняет capacity semantics**: per-live-session caps agents/completions не заменяют прежний совокупный cap. До реализации нужно выбрать владельца aggregate admission budget без SessionId-based ownership lookup, сохранить обоснованный общий предел и проверить saturation/release между live generations/epochs. Не вводить unbounded sessions под формулировкой «лимиты сохранены». Конкретный budget owner остаётся implementation gate.

Ссылки AgentRecord → host → scope не должны образовывать неисчерпаемый strong cycle. Close обязан очищать owner/history/queues после завершения monitors; где lifetime не требует ownership, использовать Weak. Проверка освобождения старого scope обязательна.

### 6. Publication и I/O barrier: отдельная обязательная граница

Простой stop token и abort task не доказывают «нет поздних эффектов». `EventEmitter::emit` держит seq mutex через произвольный async sink; `JsonlEventStore` может уже запустить filesystem работу; SessionStore deliberately передаёт admitted transaction в `spawn_blocking`, переживающий отмену caller.

Поэтому успешный shutdown требует владения completion **фактических** publication/recording effects, а не только executor future. Для in-memory pending/collaboration completion достаточно синхронной публикации до release guard. Для async effect fence должен оставаться у admitted effect owner до его реального окончания. Нельзя освобождать guard только потому, что был abort JoinHandle caller.

Минимально безопасная политика для неизвестного/stalled sink: остановить/reap peer ресурсы независимо, сохранить Closing/Failed и вернуть/сохранить явную ошибку, если завершение effect не подтверждено; не разрешать delete/reopen/replacement как successful close. Не обещать bounded successful shutdown для произвольного sink. Ожидание без deadline тоже допустимо только как явно незавершённый close, не как успех.

Отдельная граница: HTTP `watch_server` обрабатывает уже queued `Shutdown` и публикует `SessionActivityUpdated` асинхронно. Этот slice не обещает отсутствие такой последующей доставки/производной activity. Если UX/storage lifecycle потребует полного transport drain, watcher/bridge completion включается отдельным owner в barrier; обычный runtime-scope guard автоматически его не покрывает. Same-ID reopen нельзя атрибутировать по запоздалой transport activity без проверки live generation.

Если для настоящего effect ownership нужна правка EventSink/recorder contracts, выделить её отдельной зависимостью и пройти соответствующие consumers/gates. Не включать непроверенный redesign автоматически в «маленький shutdown fix». Именно эта граница, вместе с scope-bound facade construction, блокирует честный минимальный runtime patch в текущем окружении.

## Shutdown API и ошибки

Предлагаемый внутренний state machine: Open → Closing → Quiesced; failure закрывает admission навсегда и сохраняет sticky error, но **не** объявляет quiescence. Shutdown manager принадлежит scope, его shared outcome могут ждать несколько callers. Отмена одного waiter не отменяет kill/reap/reader/publication cleanup. Пока cleanup не подтверждён, ownership и quarantine остаются живы.

Порядок shutdown:

1. Закрыть admission root runs и agent scope до первого ожидания; инициировать stop во всех target scopes до ожидания какого-либо одного.
2. Сигнализировать cancel root work и stop peers/readers, разблокировать pending human-response paths. Не начинать с бесконечного ожидания `close_runs`, оставляющего peers живыми.
3. Собрать результаты root settlement, peer supervision, pending/collaboration monitors и effect fence. Cleanup siblings продолжается при ошибке одного owner.
4. Только при полной quiescence разрешить финальный successful result/Shutdown publication и смену или удаление session. При error сохранить причины и owner state; повторный shutdown возвращает ту же ошибку, не success по опустевшему registry.

`AppServerHandle::shutdown -> Result<()>` протягивается через stdio explicit shutdown/EOF/NewSession, HTTP all-session shutdown/delete, ACP close/transport-error и direct `delete_session`. Использовать текущую error response shape, без новых wire variants. HTTP aggregate должен попытаться остановить **все** sessions и вернуть aggregated error, а не short-circuit и не выдавать общий success. ACP clean close и transport error не должны затирать cleanup error; при двух ошибках сохранить обе причины.

Полный HTTP host shutdown дополнительно закрывает admission `new_session/resume/remember_server` **до** получения all-servers snapshot. Уже начатые launches зарегистрированы в host lifecycle и либо включаются в close, либо отменяются с подтверждённым cleanup до aggregate success. Снимок без такого fence даёт только shutdown выбранного набора, не остановку всего host. Не делать await под HTTP registry mutex; гонка snapshot/remember_server обязательна в тестах.

Stdio NewSession не запускает replacement после failure. Текущий bridge lifecycle надо изменить так, чтобы после остановленного bridge и неудачного close не продолжать обработку обычных запросов с partially retired runtime. Безопасный исход: вернуть request error, оставить admission закрытой и закончить транспорт с cleanup error, либо заранее определить закрытый recovery mode; не молча восстановить Open.

## Порядок реализации и release gates

1. Scope identity + typed binding + cancellation-safe shutdown result (unit tests и integration на двух sessions/reload/reopen).
2. Supervisor/reader completion и RAII pool/lease cleanup (реальные OS fixtures, natural exit/inherited stdout/error injection).
3. Pending и collaboration monitors, scoped facade/history ownership, отсутствие strong cycles.
4. Подтверждённый publication/effect barrier; если требуется contract redesign, закончить его отдельным reviewed change до заявления полноценного slice.
5. Result propagation по всем transports и storage lifecycle; только после этого публиковать integrated source patch.

Этапы можно review-ить отдельно, но ни один промежуточный этап не называется полным shutdown fix. Future patch должен применяться к зафиксированному tree, иметь `git diff --check`, `cargo fmt --all --check`, целевые runtime tests и требуемый полный gate согласно `docs/development/testing.md`. Из-за runtime wiring/нескольких crates subset tests не заменяют workspace gate. Tests → независимый review → только затем решение о публикации. Публикация integrated runtime patch до выполнения этих gates не допускается; этот пакет содержит только дизайн.

Сценарии и точные negative oracles находятся в `TEST-CONTRACTS.md`.
