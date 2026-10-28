# Bounded compaction candidates — исходниковый Rust-прототип

**Реализован небольшой host-owned компонент, а не ещё один compaction hook.** Он
владеет ограниченным набором кандидатов, отбрасывает устаревшие результаты,
удерживает занятый слот при отмене до фактического settlement и разрешает попытку
установки только через явную host-транзакцию. Код не запускает модель и не меняет
историю самостоятельно.

**Статус:** source-only, 28 октября 2026. Сборка, `cargo check`, тесты, форматтер,
clippy и CI **не запускались** по указанию пользователя. Тестовые исходники
написаны для его локальной проверки; утверждения «тесты проходят» нет.
Production workspace, Core, Modules и SDK v3 не менялись. Это не готовая live
интеграция и не доказательство ускорения.

## Что находится в каталоге

- `src/lib.rs` — самостоятельная библиотека на `std`, без зависимостей, runtime,
  сети, процессов, filesystem I/O, `unsafe` и фоновых потоков.
- `tests/policy.rs` — adversarial сценарии владельца и небольшой fake transaction.
  Fake не является адаптером Core и не реализует криптографическое хеширование.
- `Cargo.toml` — изолированная research workspace, `publish = false`.

Прототип продолжает результаты `reports/pi-opencode.md` и
`reports/codex-claude.md` из пакета исследования Proteus от 2026-10-28. В Codex
интересна optimistic installation подготовленного prefix; в OpenCode — deferred
adoption без преждевременного изменения prompt-cache prefix. Данный код —
собственная узкая policy/ownership реализация, не перенос чужого runtime.

## Главная граница: operation_gate остаётся обязательным

В прочитанном Core
[`125a9eb4088991513e9f61d899469be2076e266c`, `workflow_host.rs`](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/workflow_host.rs)
`prepare_context` берёт `operation_gate.try_write()` и отдельно требует закрытый
model stream. Model/tool operations используют read side этого gate.
[`context_preparation.rs`](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/context_preparation.rs)
привязывает результат к target execution/revision, проверяет ответ hooks;
сохранение остаётся у workflow checkpoint.

Поэтому здесь **нет** следующего:

- вызова `prepare_context` параллельно активной модели или tools;
- фонового потока внутри `TurnSettled` или продления invocation-bound authority;
- обхода host capability прямым provider request;
- переключателя, автоматически включающего speculative compaction;
- SDK export, модуля процесса или обещания, что текущий Core принимает late callback.

Для настоящего speculative model request нужен отдельно спроектированный и
реализованный session-owned lifecycle в Core: authority, quota, task handle,
cancel/join, attribution/usage, owner shutdown и checkpoint transaction. Пока
такого адаптера нет, существующий foreground compactor остаётся рабочим путём.
Эта библиотека позволяет отдельно проверить правила владения и пригодности.

## Инварианты владельца

| Свойство | Реализация |
|---|---|
| Один owner на session incarnation | `SessionIdentity`, закрытые поля `CandidateId`; key содержит session, incarnation и монотонный sequence |
| Ограниченное количество | По умолчанию 1, допускается 1–4; preparing, cancel-requested и uncertain commit занимают слот |
| Ограничение payload | Snapshot + максимальный replacement резервируются до settlement; ready держит только фактический replacement |
| Нет автоматического вытеснения работающего job | При переполнении `Capacity`/`ByteCapacity`; отмена не означает освобождение |
| Prefix CAS | Digest + количество + первый/последний message ID; append-only suffix разрешён |
| Контекстная совместимость | Provider, model, workflow, instructions, history/configuration/policy epochs, session incarnation |
| Старый callback не затрагивает новый job | ID не переиспользуются; чужой/повторный terminal callback не освобождает слот и не добавляет usage |
| Отменённый job не становится ready | `CancelRequested` всегда приводит к discard после terminal settlement |
| Повторная проверка перед установкой | `finish` и `try_adopt` независимо проверяют source; host выполняет окончательный CAS |
| Никакой установки при busy | Active model/tools/open stream дают deferred; execution cancellation — discard |
| Неясный commit не повторяется | Fence ставится **до** mutating callback; `Unknown`, некорректный receipt и unwind оставляют `CommitUnknown` |
| Утрата summary не стирает стоимость | Accepted terminal usage учитывается до stale/failure/cancel/size rejection |

Гарантия bounded относится к числу записей и удерживаемым/заявленным payload
bytes **в рамках протокола владельца**, а не к RSS процесса, сетевого клиента или
провайдера. `SourceSnapshot::snapshot_bytes` — проверяемая host декларация;
компонент не видит snapshot allocation. Worker reply нужно ограничивать при
чтении/декодировании **до** создания `Box<[u8]>`, иначе проверка размера уже не
предотвратит временное oversized allocation. Metadata имеет фиксированный размер;
owner не хранит бесконечный журнал завершённых ID или событий.
`Debug` worker result и owner печатает только размеры/счётчики, не replacement
bytes и не retained anchors, в том числе при `CommitUnknown`.

## Состояния и отмена

```text
reserve                         mark_dispatched
  Reserved -----------------------> Preparing
      | cancel                          | finish + compatible result
      v                                 v
   removed                            Ready -- try_adopt + host transaction --> removed
                                        |                           committed / rejected
Preparing -- cancel --> CancelRequested |
                            |           +-- uncertain/panic --> CommitUnknown
                            | finish                          | durable reconciliation
                            v                                 v
                         removed                            removed
```

`reserve` — учёт capacity, **не разрешение на модельный вызов**. Host должен
получить корректный immutable snapshot и его bounded size в собственной capture
boundary. Если материализация/dispatch ещё не произошли, `Reserved` можно
удалить сразу. `mark_dispatched` вызывается **перед** передачей работы worker.
Неопределённый результат dispatch нельзя считать «не запустился» и повторять.

После `mark_dispatched` отмена возвращает `SignalWorker`; host передаёт сигнал
принадлежащей ему задаче, но слот остаётся занят. `finish` допустим только после
фактического окончания задачи/сетевого запроса и отсутствия будущих callbacks.
Snapshot buffers этой задачи к этому моменту должны быть освобождены; внешние
долгоживущие копии не покрываются reservation библиотеки.
Cancel ACK, возврат из внешнего timeout и потеря receiver таким доказательством
не являются. Внешний watchdog может подтвердить termination и затем вызвать
`finish(WorkerResult::Cancelled, Usage::Unknown, ...)`, но не должен выдумывать
нулевой расход или settlement.

`shutdown` закрывает admission, удаляет reserved/ready, возвращает bounded списки
нужных cancel и reconciliation. Host обязан сохранить owner/job handles до
`is_empty()`. Повторный shutdown возвращает оставшиеся сигналы. Обычный `Drop`
**не** умеет останавливать внешние задачи и не является корректным shutdown.
Deadline/TTL здесь не запускают таймер: host вызывает `cancel(..., Expired)`.

## Как именно работает compare-and-replace

1. Host создаёт `SourceSnapshot` из authoritative session view. В нём фиксируется
   **только заменяемый prefix**, а не полный будущий контекст.
2. Worker возвращает replacement envelope: summary **вместе с retained anchors**.
   Он не выбирает session, epochs или authoritative prefix; эти поля сохранены
   владельцем при admission, ответ worker их не перезаписывает.
3. На `finish` свежий host observation проверяет ту же prefix boundary. Смена
   provider/model/workflow/instructions/epochs или prefix отбрасывает результат.
   Новые сообщения в suffix и увеличение history revision сами по себе допустимы.
4. При реальной необходимости compaction host получает transaction и вызывает
   `try_adopt`. Пока модель/tools/stream активны, ready остаётся без применения.
   Ошибка чтения до записи тоже сохраняет ready, не запускает повторный model job.
5. `HostTransaction::compare_and_replace` обязан в одной защищённой операции:
   - реально удерживать существующий operation gate и session/history lock/CAS;
   - повторить проверки source identity, cancellation и `observed_revision`;
   - проверить схему replacement, preserved anchors и связи tool call/result;
   - пересчитать **полный** будущий provider context: instructions, tools,
     replacement, anchors и актуальный suffix;
   - заменить только prefix, не потерять и не поменять suffix;
   - записать durable checkpoint/idempotency key и увеличить history revision
     (а также history epoch для последующих кандидатов).
6. `Committed` закрывает candidate. `OverBudget`, invalid anchors, stale CAS или
   доказанный no-commit отказ удаляют его; host выбирает existing foreground path.
   `Busy` сохраняет ready. Эта библиотека сама не повторяет модельные запросы.

**`HostObservation` — данные, не право и не блокировка.** Rust trait выражает
необходимый договор, но не доказывает, что implementor его соблюдает. Внешний
adapter не может прочитать state, отпустить gate, а потом считать проверку
достаточной. Для async Core потребуется корректный transaction lifetime через
await; синхронный интерфейс этого source-only прототипа такого адаптера не даёт.

## Digest и epochs: требования к host

`Digest([u8; 32])` — непрозрачное значение. Компонент его сравнивает, **не**
вычисляет и не считает доверенным результатом модели. Production host должен
использовать collision-resistant hash, например SHA-256, с versioned,
domain-separated, length-delimited канонической сериализацией. Не подходят
`DefaultHasher`, hash только по message IDs или случайная JSON map iteration.

Prefix digest включает message IDs, roles, содержимое, tool call/result identity,
attachments/blob identities и все другие model-visible данные. Прототип не
определяет канонический формат Proteus и не умеет проверить корректность digest.
Отдельные fingerprints обязаны различать:

- provider: конкретный backend/endpoint, credential/account identity без секрета,
  revision преобразования запроса и существенные настройки;
- model: полный идентификатор, revision/variant и параметры, меняющие смысл summary;
- workflow: реализацию/версию и существенную семантику контекста/anchors;
- instructions: всю существенную системную инструкцию и persistent rules.

Изменения policy/configuration повышают соответствующий epoch; reset/rewrite или
принятая compaction повышают history epoch. Обычный append suffix его не меняет.
Epoch/revision не оборачиваются и не используются повторно. При перезапуске owner
получает новую incarnation; старые результаты должны быть отклонены. Устойчивый
replay и выдача incarnation — обязанности Core, не этого in-memory компонента.

## Неясный commit и стоимость

До обращения к mutating host callback entry переводится в `CommitUnknown`.
Поэтому даже если host поймает panic/unwind после возможной записи, следующий
`try_adopt` **не** повторит операцию. `NotCommitted(Busy)` явно возвращает ready
только потому, что host доказывает отсутствие записи.

При timeout/отмене/ошибке хранения с неизвестным исходом host возвращает `Unknown`.
`cancel` такого entry требует reconciliation, а не удаляет его. Host читает
durable transaction result по `CandidateId` и вызывает `reconcile`. Без
доказательства entry удерживается. Подтверждённый no-commit удаляет candidate,
не переигрывая mutation автоматически. Receipt с неувеличенной revision не
считается доказательством успешной записи.

`UsageTotals` считает input/output tokens и settled jobs независимо от принятия
summary. `Usage::Unknown` отдельным счётчиком сигнализирует об открытом учёте;
это не ноль. Счётчики `u128` с явным saturation flag, без wraparound. Это **не**
биллинг, не деньги, не durable usage log и не учёт расходов незавершённого запроса.
Host сохраняет provider usage по своему request ID даже при process crash,
late billing correction или отбрасывании результата. Повторные callbacks не
разрешается использовать как корректировку этих terminal counters.

## Локальная проверка пользователем

В этой сессии команды ниже **не выполнялись**. Из данного каталога пользователь
может самостоятельно выполнить:

```sh
cargo test --manifest-path Cargo.toml
cargo clippy --manifest-path Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path Cargo.toml -- --check
```

Непроверенное форматирование может потребовать `cargo fmt`; компиляция и clippy
также не подтверждены. Нет зависимости, которую нужно скачивать, и нет build.rs.
Наличие тестовых исходников не означает проверку поведения реального Core.

Написанные сценарии покрывают:

- неявный dispatch запрещён; one/few capacity и aggregate byte reservations;
- отмена до/после dispatch, поздний duplicate/foreign-incarnation callback;
- prefix digest/IDs/length, все identity/epoch axes, revision regression;
- append-only suffix preservation и повторную проверку stale ready candidate;
- каждый из active model/tools/open stream, execution cancellation;
- empty/oversized/failure/unknown usage и отсутствие двойного accounting;
- окончательный host CAS после смены policy между observation и commit;
- бюджет replacement **плюс новый suffix**;
- uncertain commit, неверный receipt, panic fence и durable reconciliation;
- shutdown с reserved/ready/running/uncertain entries.
- отсутствие replacement/anchor bytes в `Debug` result и owner.

Перед реальной интеграцией нужны дополнительные Core-тесты: настоящие gate и
stream cursors, отмена между final CAS и checkpoint, kill/restart и durable
reconciliation, сохранение typed anchors/ephemeral context, точный provider
budget, privacy/permission invariants, bounded snapshot/transport, provider quota
и отсутствие late authority. Здесь они не заявлены реализованными.
