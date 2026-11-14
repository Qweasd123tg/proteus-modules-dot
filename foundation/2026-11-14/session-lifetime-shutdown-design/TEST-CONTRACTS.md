# Regression contracts: session lifetime shutdown

Статус всех строк: **PROPOSED, NOT IMPLEMENTED, NOT RUN**. Это не лог успешных tests и не замена Rust/OS integration gates. База и source facts описаны в DESIGN.md. Тесты должны управлять гонками через oneshot/barrier/test hooks, а не надеяться на sleep. Внешний timeout ограничивает зависание теста, но не служит доказательством правильной синхронизации.

## Группа A. Identity, admission и epochs

**A1. Cross-session isolation.** Две live sessions одновременно используют один cloned registry/одинаковую роль/cwd, но разных peer owners. Close A. Oracle: A admission rejected, её PID reaped/reader joined; B PID жив, followup/typed response и journal B продолжаются. Не принимать «A упала» как проверку B.

**A2. Reload epochs.** В E0 запустить active child и оставить idle child; reload E1 и запустить ещё child. Close live session. Oracle: peers обеих эпох завершены; сохранённый E0 service не может spawn/send/resume; никакой current-epoch-only обход.

**A3. Same SessionId reopen, task surface.** Закрыть live generation A, открыть B с тем же durable ID. Старые pending handle/task_id из A дают explicit rejection, свежий spawn B успешен. Одновременно хранить старый Arc service, чтобы тест не прошёл благодаря простому Drop.

**A4. Same SessionId reopen, collaboration surface.** A содержит `/root/review`, unread completion и history; B использует тот же ID и path/generation. `list/send/followup/interrupt/wait` в B не видят owner/completion A. Запоздалые history-bind и `control.complete` A не меняют B. Control B продолжает normal workflow.

**A5. Coherent binding.** Из одной PreparedAssembly построить две live sessions; проверить scoped service и все зарегистрированные facade tools обеих. Модельные инструменты после `tools_for_model` и reload остаются bound к правильному scope. Добавить отрицательный тест доступного supported пути смешивания old tools/new context; если такой путь нельзя исключить конструкцией, требуется проверяемый identity contract, а не только SessionId.

**A6. Admission vs close.** Pause до регистрации guard, после регистрации/до reserve, после reserve/до SubagentStarted await, до OS spawn и сразу после OS spawn. На каждой границе close либо отклоняет ещё не admitted operation, либо ждёт её tracked rollback/cleanup. В обоих исходах нет untracked process, stranded reservation/permit/history. Повторить close и убрать первый waiter.

**A7. Reload vs close.** Pause до и после persistence commit reload. Closing не публикует новую действующую agent admission. Failed pre-commit binding не меняет текущий config/epoch. Не допускается новый fallible шаг после commit, создающий disk/runtime divergence.

**A8. Aggregate capacity.** Заполнить выбранный общий session-control budget несколькими live sessions/epochs; ещё одна admission отклоняется до allocation/spawn. Closing/cleanup failure не освобождает capacity преждевременно; подтверждённое освобождение позволяет новую session. Per-session agent/completion limits проверяются отдельно и не подменяют совокупный cap. До выбора budget owner этот test остаётся blocked design decision.

## Группа B. Process/reader lifecycle

**B1. Idle and reserved stop.** Idle peer держит stdin/stdout открытыми; другой peer reserved в ожидании role permit. Close. Oracle: оба direct PIDs reaped, readers joined; rollback не возвращает reserved peer в idle, history expired.

**B2. Active blocked paths.** Отдельно: blocked stdin write, waiting approval, waiting user input, no-output peer, awaiting role semaphore. Close разблокирует каждый путь без зависимости от stdout EOF; закрывает mailbox и освобождает permit/bookkeeping. Captured bytes доказывают, что partial frame не дописан Cancel, а не только конечную смерть PID.

**B3. Natural terminal then exit.** Fixture пишет valid terminal Response и сразу выходит. Pause consumer до child exit и держать queued terminal непрочитанным. Oracle: consumer получает именно terminal result, затем clean EOF; не health-error раньше terminal, не потерянный final frame. Прогнать несколько scheduling orders, включая exit до reader завершения.

**B4. Inherited stdout.** Fixture создаёт helper, удерживающий stdout после выхода direct peer. Explicit shutdown не ждёт EOF helper: direct peer reaped, reader explicitly stopped/joined. Тест в finally сам завершает helper. Не заявлять, что runtime убил descendant.

**B5. Reader failure semantics.** Existing overflow/invalid JSON tests остаются fatal, buffered response после invalidated stream не превращается в success. Expected abort от supervisor stop отличать от injected reader panic/unexpected cancellation.

**B6. Kill/reap errors.** Fault-injection adapter отдельно возвращает kill error, wait error и reader join error, затем пару ошибок одновременно. Oracle: ошибки сохранены/агрегированы, scope не Quiesced, admission закрыта, повторный/concurrent shutdown видит ту же причину. Reader stop/join всё равно предпринимается при kill/wait error, reap не пропускается при reader error; остальные children получают stop. Добавить race уже reaped process vs kill: допустимый success только с подтверждённым reap и reader completion.

**B7. Drop ownership.** Drop active/idle ChildProcess, outer execution future и последнего user shutdown waiter. Oracle: supervisor продолжает cleanup; его own completion принадлежит scope, не пропадает с caller. Слабые ссылки подтверждают eventual release после успешного cleanup, без strong cycle.

## Группа C. Publication и effect ownership

**C1. Pending monitor fence.** Pause monitor после execute completion, до PendingOutcome.complete. Close не отвечает success раньше публикации/явного settlement. После success replay barrier не порождает новой completion.

**C2. Collaboration monitor fence.** Pause после `host.wait_agent`/PendingOutcome consume, до `control.complete`. Close обязан ждать этот второй monitor. Повторить с same-ID reopen и одинаковой agent generation. Это отдельный gate от C1.

**C3. Stalled SubagentStarted/SubagentFinished.** Управляемый sink зависает до/после first append. Peer cleanup выполняется независимо. Если effect completion не подтверждён, shutdown остаётся незавершённым/Err и не разрешает NewSession/delete. Releasing sink либо даёт tracked completion, либо остаётся диагностируемая ошибка; одного abort caller недостаточно.

**C4. Detached filesystem work.** Sink/recorder передаёт append в paused blocking worker, caller future отменён. Oracle: нельзя объявить successful quiescence или удалить storage, пока worker не завершён/не отклонён подтверждённым retirement fence. После success hashes журналов/event log стабильны при отпускании всех stale task barriers. Проверять реальные файл/директорию, а не mock flag.

**C5. RAII execution cleanup.** Abort в каждом await между prepare, permit, lease, send, event forward, pool release и final emit. Oracle: нет stranded leased/reserved entries, mailbox delivery lock, role permit или живой history retention; stopped scope нельзя «реанимировать» поздним release.

**C6. Producer vs queued transport.** Pause HTTP watcher до получения уже queued Shutdown; successful producer barrier не выдаётся за завершённый transport drain. После отпускания watcher возможна предусмотренная activity delivery, но она не создаёт новый runtime effect и не изменяет новую same-ID live generation. Если требуется transport quiescence, включить watcher в owner barrier и изменить этот oracle явно.

## Группа D. API/storage lifecycle

**D1. Stdio failure.** Inject cleanup error в Shutdown и NewSession. Existing response `ok=false/error` сохраняет причину; replacement не запускается; дальнейшая admission запрещена. EOF cleanup error возвращается caller, не теряется за writer/bridge join. Verify bridge termination ordering.

**D2. HTTP aggregate.** Минимум три sessions, первая cleanup failure. Все три получают stop до ожидания; результат aggregate Err содержит session-specific causes, activity не выдаёт общий successful close. Повторный запрос не забывает failure после изменения cache. Дополнительно pause new_session/resume до launch, после launch и до remember_server одновременно с all_servers snapshot: новая admission после host fence отклоняется, ранее admitted launch обязательно включён в cleanup до aggregate success.

**D3. Delete quarantine.** Cleanup failure оставляет storage и live owner registration/quarantine доступными для диагностики; `remove_session_server` и `delete_owned` не вызываются. При успехе сначала settlement/effect barrier, потом removal. Отмена HTTP waiter не прерывает admitted delete task.

**D4. ACP/direct API.** Clean EOF, transport error и неудачный `start_session` проходят одинаковый cleanup. Первичная и cleanup ошибки не затирают друг друга. Direct `delete_session` также не удаляет после неуспешного close.

## Группа E. Сохранённые условия, отрицательный контроль

**E1. PR87–89 preservation.** Повторить process_agent_control/process_agent_pool, user_input, turn_progress, approval cache scopes на final code. Cooperative role timeout и обычный user cancel сохраняют target/full-frame/ACK/partial-text/grace rules, resume when valid, descendant origin и opaque queue IDs. Перекрывающиеся scopes не суммировать как уникальные tests.

**E2. Background routing negative.** Повторить root → parent → background leaf question после завершения foreground parent. Если без отдельной routing-реализации вопрос по-прежнему не доставлен, это ожидаемый открытый gap, не пройденный delivery test. Result shutdown slice не переименовывать в background-delivery fix.

**E3. Journal/cold history.** Поддерживаемые canceled/timeout сценарии имеют правильный TurnSettled, cold history не изменяет hashes. Поддерживаемые root Success/Error проходят настоящий workflow replay согласно upstream matrix. Cold history не именуется replay.

## Команды после появления toolchain и implementation

Сначала прочитать `Core/docs/development/testing.md`, подготовить совместимый Modules reference fixture штатным runner. Ниже команды задают существующие regression scopes, не утверждают, что новые тесты уже существуют:

```sh
python3 scripts/test.py -p proteus-core --offline --test process_agent_control --test process_agent_pool -- --nocapture
python3 scripts/test.py -p proteus-core --offline --lib --test process_agent_pool user_input -- --nocapture
python3 scripts/test.py -p proteus-core --offline --lib --test process_agent_pool app_server::turn_progress -- --nocapture
python3 scripts/test.py -p proteus-core --offline --lib --test process_agent_pool core::approval::cache -- --nocapture
cargo fmt --all --check
git diff --check
```

Размещённые новые lifecycle/app-server tests запускать явными actual package/target/filter, убедиться в ненулевом числе selected tests. Focused scopes нужны при разработке; финальный полный `python3 scripts/test.py full` включает пересекающиеся Rust targets и не требует затем повторять их без новой правки/причины. Для runtime wiring полный gate и применимые external-consumer checks обязательны: одних focused scopes недостаточно. Новые команды уточнять по реальному diff, не заводить фиктивный `session_lifetime` filter заранее. Собирать final tested tree, команды, counts, logs и все непройденные gates; независимый review не заменяет executable checks.
