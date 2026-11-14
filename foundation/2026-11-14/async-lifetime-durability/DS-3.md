# DS-3: dropped direct run допускает durable append, но оставляет warm history authoritative

## Статус

**P2 conditional source-only кандидат для прямого Rust `AgentRuntime` API.** Rust метод `pub`, но architecture docs прямо называют эту surface внутренней и исключают её прямой вызов product clients (`docs/architecture/architecture.md:218–221`). Нужен dropped/aborted Rust future при незавершённом accepted append. Не путать со штатным `CancellationToken`, закрытием HTTP-клиента или crash всей программы. Реальный Rust/Tokio/HTTP сценарий не исполнялся; ниже причинный путь и предложенный deterministic regression.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + PR87–89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. PR91 новых production changes не содержит. Ничего не изменено в Core.

## Источник рассогласования

Две полезные гарантии реализованы на разных lifetime:

- `SessionStore::write_transaction` (`core/session_store/writer.rs:112–133`) передаёт writer lock и append в independent `spawn_blocking`. Отмена awaiter не отменяет принятую durable operation. Существующие `session_store/cancellation_tests.rs` прямо проверяют завершение successful append после abort caller.
- `AgentRuntime::persist_current_user_message` (`core/runtime/turn.rs:478–500`) держит warm history lock, ждёт `store.append_history(...).await`, **после ACK** выполняет `history.push(user_message)`, revision increment и history-turn update. Warm reconciliation не принадлежит durable worker.

Если future отменён во время `.await` после запуска worker, journal допишется, а warm update уже некому выполнить. Future drop освобождает history/run locks. `SteeringRunGuard::drop` (`runtime/steering.rs:357–376`) освобождает reservation/queue, но не меняет `history_resident`/deferred validation. Комментарий прямо предусматривает task abort transport-ом; это не только произвольное использование приватного helper.

Нормальный `run_reserved_chain` в конце вызывает `release_history` (`runtime/turn.rs:104–154`), но при drop control flow до этого `await` не доходит. Таким образом, surviving runtime остаётся с `history_resident=true` и старым `history`, хотя writer validation/history уже новее.

## Минимальная последовательность

Используем H как исходную canonical/warm history, A — user message прерванного вызова, B — следующий user message. Сохраняем сам runtime живым.

1. `runtime.run(A)` открывает turn и доходит до `persist_current_user_message`. Durable append A принят, blocking worker удержан test barrier до записи.
2. Внешний caller abort-ит/drops **run future**, не cancellation token. Run guard снимает reservation; `release_history` не исполняется; warm = H, resident=true.
3. Worker отпускается и успешно commit-ит A. Durable = H+A. Writer mutex сохраняет порядок, поэтому следующий writer не может обогнать A.
4. Уже теперь `runtime.history()` возвращает H (`runtime.rs:402–409`). `conversation_snapshot()` способен вернуть H с **новой durable revision** (`runtime/conversation.rs:39–54`): messages берутся из warm buffer, revision из `store.history_revision()`.
5. Следующий direct `run(B)` вызывает `validate_cached_resume`. При `deferred=false && history_resident=true` функция немедленно выходит (`runtime/resume.rs:18–32`), не сверяясь с durable revision.
6. Turn B открывается на правильной writer revision; `persist_current_user_message(B)` добавляет B и в durable, и в текущий warm buffer. Получается durable H+A+B, warm H+B. Именно H+B передаётся workflow.
7. Для простого успешного workflow без compaction/checkpoint **и с отключёнными active hooks**, который возвращает новый assistant Y, proposed terminal history = H+B+Y. `commit_history_update` сначала восстанавливает H+A+B из writer (`runtime/history.rs:137–156`), затем отклоняет неподходящий prefix (`181–185`) с `workflow terminal history disagrees with committed checkpoints`. При active hooks Core сам checkpoint-ит candidate в `reviewed_workflow.rs:88–97`, даже если fixture Workflow не делает checkpoint; тогда базовое stale-history рассогласование сохраняется, но первый failure может быть раньше terminal.

Следствие 4 является самостоятельной coherence-проблемой; пункт 7 — конкретный дополнительный failure path для описанного non-compacting workflow. Если workflow уже выполнил модель/tool, это происходило на неполной warm history до обнаружения расхождения. Реальные платные запросы, повтор effects или публичный UI-инцидент не воспроизводились и не заявляются.

После нормального завершения/ошибки B unload может восстановить согласованность следующего run. Поэтому не утверждается вечная блокировка session, потеря durable A или порча journal.

## Scope controls

- **Не стандартная cancel token ветка.** Cooperative cancellation даёт `run_one_turn`/`run_reserved_chain` закончить settlement/release и требует отдельного regression, который должен остаться исправным.
- **Не обычный HTTP disconnect.** `AppServerHandle::admit_user_message` (`app_server/runs.rs:181–195`) владеет run в отдельном `tokio::spawn`; dropped reply receiver сам по себе его не abort-ит. Данный finding не утверждает HTTP/GUI достижимость без дополнительного owner-abort path. В просмотренных production callers такой дополнительный прямой abort-путь review не обнаружил.
- **Не прямой product API контракт.** `docs/architecture/architecture.md:218–221` называет `AgentRuntime::run` внутренним Rust путём и прямо говорит, что product clients его не вызывают. Кандидат относится к internal/embedding direct callers, не доказывает достижимость из штатного продукта.
- **Не cold restart.** Новый runtime строит history из journal и не сохраняет старый resident buffer.
- **Без persistence нет independent durable append**, значит именно эта split-commit цепочка отсутствует.
- **При failed append с успешным rollback** durable A нет; это обязательный negative control.
- В `clear_history` уже использован другой ownership pattern: отдельный worker владеет durable mutation, reconciliation и unload (`runtime.rs:348–384`). Это подтверждает, что вопрос не решается одним SessionStore mutex для всех callers.

## Предлагаемый regression, НЕ РЕАЛИЗОВАН И НЕ ЗАПУЩЕН

1. В unit module Runtime создать persistent runtime с маленькой deterministic workflow, сохраняющей полученный `history` и возвращающей один assistant message без checkpoint/compaction/model/tool. **Active hooks отключить**: только тогда reviewed-workflow wrapper не добавит собственный checkpoint (`reviewed_workflow.rs:51–53,88–97`). Начальная H может быть пустой.
2. Через `TurnStarted` test sink barrier остановиться **до user append**, затем вызвать существующий `SessionStore::pause_next_append` и отпустить sink. Дождаться сигнала, что именно user `HistoryMutated::Append` worker принят и paused. Не ставить pause вслепую до `TurnOpened`.
3. Abort spawned direct `runtime.run(A)` task; дождаться canceled JoinError, затем отпустить append с successful write. Дождаться writer fence через следующий read/lock. Сам Arc runtime оставить живым.
4. Сравнить `runtime.history`, `runtime.conversation_snapshot` и cold `store.load_messages`: desired invariant — одинаковая history/revision либо явная deferred recovery до её публикации. Не принимать «старые messages + новая revision».
5. Выполнить B. Desired invariant — workflow видит A+B, успешный результат проходит terminal history validation. Отдельно current observational oracle фиксирует H+B и terminal disagreement, но такой PASS не означает исправление.
6. Контроли: failed append/rollback; cooperative token cancel; ordinary success; abort до admission; cold re-open. Поддерживаемое поведение queued inputs при abort сохранить отдельно.

Отдельная иллюстративная модель (не включена в пакет) моделирует только перечисленные transitions и prefix equality. Три случая: successful detached append, failed append control, recovery-before-next-run control. Это не исполнение Rust, не доказательство Tokio scheduling, не benchmark.

## Системное упрощение

Один ownership contract должен охватывать **durable append + warm publish/invalidation + release of run admission**, а не раздельные гарантии на каждой переменной.

- Вариант A: admitted direct run получает owner task, а caller только ожидает outcome, как уже сделано для clear/settings/app-server runs. Но это меняет drop semantics: нельзя молча продолжать неизвестные model/tool effects после caller drop; cancellation и ожидание settlement должны быть явными.
- Вариант B: run-drop guard синхронно отмечает session dirty/nonresident **до** освобождения admission. Следующее чтение/исполнение обязано дождаться accepted writer work и согласовать canonical state. Недостаточно лишь сделать следующий Send reload: публичный `history()`/`conversation_snapshot()` тоже не должны выдавать stale warm buffer как current.
- Выбор следует оформить в существующей runtime/session owner границе, без нового cache/registry. Не делать journal rollback после потерянного ACK и не «лечить» mismatch удалением A: append мог уже стать canonical.

Нужны проверка lock ordering и гарантия, что marker нельзя очистить раньше финального append completion. Новая abstraction ради уменьшения LOC не предлагается; выигрыша скорости/RSS не измерено.

## Дедупликация

Прочитаны PR91, published `initial-runtime`, `round3-core`, `tool-response`, прошлые persistence/resume/history-events отчёты. Они покрывают late cancel после Success, accepted steering + failed event ACK, ответ уже умершему requester, cold crash ToolEffect и другие границы, но не surviving resident buffer после abort direct run на append.

В PR84 extracted text выполнен targeted поиск `persist_current_user`, `history_resident`, `run_guard`, dropped future/lost ACK/caller; соответствующий finding не найден. Там явно сохранено правило: lost ACK не отменяет committed history. DS-3 следует ему, а не предлагает откат. PR90 session-owned shutdown может дать подходящий будущий owner, но текущий DS-3 trigger не требует shutdown, delete, reopen или другого epoch.

Независимый source review выполнен (`REVIEW.md`): причинный путь подтверждён в узком direct-Rust scope. Поправки reviewer о внутренней surface и inactive hooks внесены. До внешней публикации требуется финальное review родительского потока; будущий Rust regression остаётся неисполненным. Здесь не заявляется исправление либо runtime reproduction.

## Закреплённые source anchors

Пути `core/...` выше относительны `crates/proteus-core/src/`. Ключевые production-файлы не изменены delivery PR87–89.

- [core/runtime/turn.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/turn.rs#L478-L500)
- [core/session_store/writer.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_store/writer.rs#L112-L133)
