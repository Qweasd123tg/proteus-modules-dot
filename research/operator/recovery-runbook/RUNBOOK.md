# После сбоя: сначала установить состояние, потом решать о повторе

**Source-only runbook для Proteus Core `1fc3ef223d10322815dd9290a50d045bc95402bb`.** Команды, HTTP-запросы, пользовательские сессии, modules/providers и replay здесь **не запускались**. Формы ниже проверены по dispatcher/producer/consumer исходникам; наличие endpoint не является разрешением обращаться к чужому серверу или читать чужую сессию. Это не новая утилита восстановления.

## 0. Зафиксировать, чего именно не хватает

Разделить шесть независимых вопросов:

1. Получен ли ответ транспорта и связан ли он с **исходным request/run ID**?
2. Есть ли сейчас admission/active run либо очередь?
3. Есть ли canonical settlement этого **конкретного turn**?
4. Что известно об операции инструмента и внешнем эффекте?
5. Совпал ли воспроизводимый workflow с записанной траекторией?
6. Проверена ли цель задачи отдельным oracle?

Сохранить уже имеющиеся идентификаторы: адрес/идентичность разрешённого сервера, `session_dir`/`session_id`, исходный request ID, известные run/message/turn/execution/call IDs, время наблюдения и точный тип ошибки. Не собирать credentials или полный контент по умолчанию. **Run ID, queued message ID, TurnId, execution ID и CallId — не одно поле.** Не связывать операции только по одинаковому тексту.

Не нажимать повторную отправку, `resume`, replay, очистку истории или restart как способ выяснить состояние. Если установлен только transport/decode error, начальная классификация — **submission outcome unknown**, а не «ничего не произошло». Для Started Core запускает session-owned работу до ACK; активный дубликат ID отвергается, но registry не является durable таблицей результатов всех завершённых запросов. [Admission и публикация результата](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/runs.rs#L79-L177), [ACK](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/http/commands.rs#L187-L239).

## 1. Сначала выбрать действительно подходящую поверхность

Полная классификация с источниками — [READ-SURFACES.md](READ-SURFACES.md). `S` ниже — **URL-encoded абсолютный путь разрешённой сессии**, `T` — известный TurnId. Это placeholders, не готовые URL и не новые flags. Если нет уже доверенного запущенного AppServer, не запускать его только ради «чтения»: launch/resume и discovery имеют отдельные последствия. Для исторического lifecycle aggregate есть отдельная CLI-ветка без загрузки runtime.

- `GET /config/local?session_dir=S`: текущая active-session summary + `activity.running_run_ids`, без новой model-catalog discovery по этому route. Отсутствующая active session даёт ошибку, не auto-resume.
- `GET /pending?session_dir=S`: current approvals/input и queued message IDs. Это live snapshot, не история доставок.
- `GET /analysis?session_dir=S&turn_id=T`: strict journal projection для конкретного turn, **в том числе cold session**, без resume/выполнения модуля. Если `turn_id` не передан, выбирается последний turn; это нельзя автоматически считать исходным запросом после потери ACK.
- `GET /history?session_dir=S`: live transcript snapshot или cold validated journal→transcript; это presentation, не все lifecycle facts.
- `proteus eval report /absolute/session-or-journal-path`: исторический lifecycle aggregate, human-readable, **без `--json`**. Успешный exit означает, что отчёт построен/выведен, не что задача успешна.

`GET /sessions` может читать весь configured catalog и обновлять disposable cache; `GET /events` устанавливает SSE subscription и вызывает `start_session`, который при первом использовании может записать SessionStarted через configured event sinks. Поэтому это не безусловно write-free «просто GET». Уже полученные в доверенном клиенте `SessionSnapshot.execution` / `ExecutionUpdated` полезны; новая подписка имеет эту отдельную границу. [Analysis](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/http/analysis.rs#L1-L112), [read routes](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/http/reads.rs#L32-L91), [SSE initial action](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/http/sse.rs#L17-L35).

HTTP security зависит от фактических bind/origin/token настроек. Не предполагать authentication по имени endpoint или автоматически публиковать URL с token. Проверенный R40 уже описывает конфигурационную границу; этот runbook её не заменяет. [R40 checklist](../EVIDENCE.md#e12).

## 2. Шесть развилок

### A. ACK не получен / клиент пишет «не отправлено»

1. Сопоставить **известный исходный ID** с текущими `activity.running_run_ids` либо уже полученными `execution.active.run_id` / `execution.last.run_id`.
2. При exact match active, если исходный ID не использовался повторно: соответствующая submission наблюдается принятой в текущем live incarnation; **не отправлять снова**. `running`/`cancel_requested` не terminal outcome. При match last: читать его status/error, но затем отделить canonical settlement и цель задачи.
3. Если сохранился queued ACK, использовать его `message_id` для `/pending`; `request_id` и `message_id` различны. При полностью потерянном ACK queued snapshot не содержит исходный request ID, только message ID/text/image_count. Совпадение текста — подсказка, не доказательство идентичности.
4. Если ID не найден, результат остаётся **unknown**: run мог уже завершиться и быть вытеснен из единственного `last`, сессия/сервер мог перезапуститься, queued item мог быть потреблён. Это не доказательство отказа admission и не разрешение blind retry даже с тем же ID.

**Gap:** нет прослеженной существующей durable completed-request lookup поверхности, связывающей любую старую submission с результатом. Ручной следующий шаг — операторская сверка имеющихся transport/admission evidence и конкретной операции; если идентичность не установлена, остановиться на unknown. Не добавлять модулю доступ к скрытым session files. [Live DTO](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/app_protocol/live.rs#L18-L43), [queued DTO](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/app_protocol/pending.rs#L42-L60).

### B. Есть active run или cancellation ACK

- `running`, `waiting_approval`, `waiting_input` описывают live control-plane состояние; последнее определяется наличием pending requests, не самостоятельным доказательством работающего OS process.
- `cancel_requested` означает, что host выставил token и опубликовал запрос отмены. Это не `canceled`, не отсутствие результата/эффекта и не rollback.
- Использовать уже разрешённое наблюдение за конкретным run до terminal status. При разрыве/перезапуске не дорисовывать settlement из исчезновения `active`; перейти к историческому turn, если его identity известна.
- Сам `POST /cancel` — **мутация**, не проверка состояния; этот runbook не предлагает его выполнять. Успешный ответ этой операции только подтверждает обработку cancel request в выбранном path.

[Cancel branch](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/runs.rs#L164-L177), [activity derivation](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/app_protocol/session.rs#L87-L122). R20 отдельно ограничивает cancellation grace кооперативным async settlement, не универсальным wall-clock/OS stop.

### C. Исторический turn завершён ошибкой, отменой или timeout

`/analysis.turns[].status` различает `success/error/canceled/timeout/unsettled`; `unsettled` значит **в прочитанном snapshot нет settlement**, не «процесс сейчас выполняется». Для выбранного `T` смотреть `selected.error`, model failures, tool resolution и result; не расширять вывод на остальные turns. Revision здесь — journal sequence, не номер текущего SSE stream.

CLI `eval report` полезен как общий контроль валидности/счётчиков, но агрегирует session; текущий незавершённый turn тоже делает его failed. Не заменять этой оценкой точечную диагностику. При read/validation error — **evidence unavailable/invalid**, не «пустая успешная история». Не чинить это очисткой, `resume` или редактированием journal. Ручной шаг — передать оператору/maintainer точные source/schema/session identity и минимально необходимую диагностику, с минимальным содержимым. [Analysis status contract](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/app_protocol/analysis.rs#L15-L56), [eval predicate](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/eval_report.rs#L38-L44).

### D. Есть tool outcome, но непонятно, был ли final result

**Существующая `/analysis` помогает, но стирает именно это различие:** обе записи `ToolEffectRecorded` и `ToolResultRecorded` кладутся в один `Tool.result`; следующая перезаписывает предыдущее значение. `finished_at_ms` этого step тоже может прийти от effect. Transcript аналогично использует effect fallback, если final отсутствует. Поэтому ни non-null result, ни отображённое завершение не идентифицируют вид исходной записи.

`result=null` означает отсутствие соответствующей записи в этой проекции, **не отсутствие внешнего эффекта**. Название `ToolEffectRecorded` само по себе тоже не physical-effect receipt: это pre-AfterTool результат, возможно уже truncated или synthesized cancellation/timeout/denial outcome. Не повторять effectful tool по этим признакам.

**Узкая host/UI gap:** показать отдельно resolved/effect/final-result facts с execution owner/call ID и sequence. Core уже хранит различимые canonical record variants и валидирует lifecycle; новый ledger не нужен. До такого consumer ручное исследование разрешённого источника должен делать host/app maintainer через существующий `SessionStore::load_projection()` и `JournalProjection.records` в своей доверенной среде. Это **library API, не готовая CLI-команда**, не назначенный здесь запуск, не raw grep и не предоставление module filesystem capability. Внешний результат проверяется отдельным разрешённым operation-specific источником; неизвестное не превращается в автоматический retry.

[Collapsed analysis consumer](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/http/analysis.rs#L190-L225), [distinct canonical validation](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_journal/projection.rs#L343-L395), [projection records](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_journal/projection.rs#L543-L553).

### E. Replay report не совпал — либо совпал с Error

Если уже имеется разрешённо полученный `WorkflowReplayReport`, читать `comparison.matched`, issues, recorded/replay status и `source_journal_unchanged`; не process exit и не слово success в prose. Matching Error — воспроизведение ошибки, не выполненная задача. Mismatch — несогласованность покрываемой траектории/источника/реализации, не приказ повторить внешнюю операцию.

Для предварительной классификации **уже выбранного файла отчёта** существует отдельный собственный R39 consumer с точным Core1fc schema1 профилем. Он сохраняет primary transport/execution/objective/evaluator states unknown и показывает только reported-match/divergence; не аутентифицирует producer и не вычисляет повторно все normalization predicates. Unsupported/invalid/inconsistent — отдельные исходы. [R39 documented use](../EVIDENCE.md#r39).

Сам `replay workflow` не пассивный reader: recorded model/tools не создают real adapters, но выбранный workflow/policy код выполняется из supplied catalog. Canceled/timeout turns намеренно не поддерживаются, multi-turn source требует `--turn-id`. `replay prompt` ещё иной: создаёт model adapter и посылает сохранённый запрос; local tool calls не выполняет, provider-hosted tools default refuses. Ни одна replay-команда в этом runbook не запускается/не рекомендуется как первый шаг восстановления. [Workflow execution](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/workflow_replay/mod.rs#L120-L165), [supported settlement](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/workflow_replay/fixture.rs#L239-L250).

### F. Turn успешен, но цель не проверена

Lifecycle success, replay match, tool success и objective verification — разные поля. Eval success не требует `tool_failures==0`; official project-check имеет собственный status в output metadata и может успешно **доставить отчёт о failed/blocked/unsupported проверке**. Даже passed command не доказывает, что собран ожидаемый ненулевой набор тестов.

Если нет независимого oracle с явными ожидаемыми postconditions, покрытием и идентичностью проверенного артефакта, финальный статус — **objective not verified**, а не «всё прошло». Следующий шаг — отдельно согласованная конкретная проверка, не безусловный запуск найденных в проекте скриптов. R39 не поддерживает выдуманный eval JSON или универсальную project-check схему. [R36 layers](../EVIDENCE.md#e10), [R39 limitations](../EVIDENCE.md#r39).

## 3. Короткая запись результата расследования

Это статический шаблон, не runtime output и не новая wire schema:

- **Identity:** точные известные IDs; неизвестные оставить неизвестными.
- **Submission:** acknowledged / observed active / explicit refusal / unknown; указать источник и время.
- **Execution:** active/cancel_requested либо recorded settlement выбранного turn; live incarnation и journal revision отдельно.
- **Tool evidence:** resolution; observed result; effect-vs-final distinction available/hidden; external outcome unknown/отдельный источник.
- **Replay:** not run / reported-match / reported-divergence / unavailable/invalid; source/config/artifact identity не выдумывать.
- **Objective:** not verified либо точный независимый oracle и его покрытие.
- **Next action:** только разрешённое чтение/ручная проверка; retry/cancel/resume/replay/тесты требуют отдельного решения владельца.

[Точные поверхности](READ-SURFACES.md) · [Покрытие и reused evidence](COVERAGE.md) · [Невыполненные end-to-end gates](GATES.md).
