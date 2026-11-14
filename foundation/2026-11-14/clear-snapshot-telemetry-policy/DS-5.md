# DS-5: concurrent conversation read объединяет pre-clear messages и post-clear revision

## Статус

**P2 source-only coherence candidate.** Условие — одновременные успешный persistent `clear_history` и read conversation snapshot. Не нужны failed write, отмена caller, crash, malformed данные или сторонний module. Детерминированная lock-последовательность ниже выведена из исходников, **Rust/Tokio/HTTP regression не запускался**. Частота в реальном UI не измерена.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. PR91–93 не меняют production. Core не редактировался.

## Причина

`clear_history` правильно имеет независимого operation owner, но не атомарную границу публикации для reader-а, собирающего snapshot из **двух** представлений.

- `core/runtime.rs:348–357`: clear берёт `run_lock`, `validate_cached_resume` возвращает history в resident state, затем owner task вызывает `store.clear_history` **не держа history lock**.
- `core/session_store.rs:264–266` и `session_store/writer.rs:279+`: durable clear — `HistoryMutated::Replace([])`. Writer transaction владеет writer mutex до commit/rollback (`writer.rs:113–133`); successful append обновляет committed history и revision.
- `runtime.rs:375–379`: только после await durable clear owner очищает warm history, history-turn, interruptions и model context. Следующий `release_history` завершает residency.
- `runtime/conversation.rs:37–54`: reader берёт history mutex, затем context mutex, клонирует resident messages и **потом await-ит `store.history_revision()`**. `session_store.rs:169–177` получает эту revision из текущего writer под его отдельным mutex.

Таким образом reader может захватить старую history до commit, дождаться нового writer revision, а своим history lock ещё и задержать warm cleanup clear-а. Returned snapshot не соответствует ни состоянию до clear, ни состоянию после него.

`proteus-contracts/src/contracts/conversation/view.rs:20–26` явно называет `source.revision` revision данного snapshot, а не SSE cursor или journal sequence. Ошибка касается пары history/revision, не того, что read, перекрывающий clear, вообще вправе увидеть прежнюю историю.

## Точная последовательность

Обозначения: до clear resident/canonical history = H (непустая), history revision = r (обычная ненасыщенная revision, чтобы r+1 отличалась от r).

1. Clear восстанавливает resident H, начинает durable Replace([]), держит writer mutex; worker остановлен existing test barrier **before_write**.
2. `conversation_snapshot` берёт history и context mutexes. Они свободны, поскольку clear ждёт writer без них. Reader выбирает resident branch и клонирует H; затем ждёт writer mutex в `store.history_revision`.
3. Worker отпущен с обычным successful write/sync. Durable history становится `[]`, revision `r+1`, writer mutex освобождается.
4. Reader получает `r+1`. Clear не может заменить warm H, пока reader держит history lock. Reader возвращает **`{messages:H, revision:r+1}`** (и pre-clear context).
5. Clear получает history lock, очищает warm state, unload-ит, возвращает success. Следующий read возвращает **`{messages:[], revision:r+1}`**.

Ни одно корректное мгновение history-state не имело H с revision r+1. Два snapshot одной history revision имеют разный messages payload. Если reader завершился полностью до начала clear, H/r допустим; если после, []/r+1 допустим. Именно смешанный результат — кандидат нарушения coherence.

## Product/API путь и пределы эффекта

`AppServerHandle::clear_history` (`app_server/runs.rs:96–112`) держит `runs` mutex и не допускает active run. Однако `AppServerHandle::conversation_view` (`app_server/conversation.rs:7–14`) этот mutex не берёт. Live HTTP `/conversation` (`http/sessions.rs:196–214`) вызывает его напрямую; `HttpAppState::server_for_session_dir` (`http/state.rs:120–127`) лишь кратко читает registry и клонирует handle. То есть source-level live read path не исключает указанное перекрытие.

Никаких действий model/tool во время clear не требуется. Не утверждаются повтор effects, нарушение execution admission, HTTP socket reproduction, конкретная реакция Desktop или постоянное возвращение cleared history. После завершения clear обычный новый read согласован; canonical storage остаётся корректно очищенным.

## Existing tests и proposed regression

Полностью прочитан `runtime/tests/clear_history.rs`. Он проверяет cancelled clear caller, failed durable clear и согласованность следующего run. Пока worker paused, вызывается `runtime.history()`, которому revision не нужна; это полезный контроль, но он не создаёт history-lock → writer-lock snapshot path. Дополнительно просмотрены conversation HTTP и resume-cache tests; отдельного clear/read revision case не найдено. Тесты здесь не запускались.

Минимальный будущий regression можно расширить в том же module:

1. Persistent runtime с H и известной r; deterministic workflow без внешней модели или tools. Получить snapshot до clear.
2. `SessionStore::pause_next_append`, spawn `runtime.clear_history`, дождаться pause. В отличие от DS-4 существующий **before_write** seam здесь подходит.
3. Установить детерминированно, что reader захватил H/context и ждёт writer. Одного sleep недостаточно. Pin + explicit poll полезен, но сам `Pending` ещё не доказывает место остановки: runtime может cooperative-yield раньше. Для pre-fix witness нужен test-only reached signal у этой границы или отдельная проверка удержания обоих locks; правильный regression после исправления должен допускать остановку reader раньше на coherent publication gate, а не требовать сохранять lock-порядок дефекта.
4. Отпустить writer через successful branch, дождаться snapshot и clear. Desired invariant: overlapping snapshot равен H/r либо []/r+1, но не H/r+1. After-clear snapshot обязан быть []/r+1.
5. Контроли: failed append/rollback → H/r; read полностью до clear; read после completion; no concurrent read; normal nonempty append/checkpoint snapshot. Проверять completed outcome, не считать observed bad tuple проходом исправленного regression.

Отдельная иллюстративная lock-модель (не включена в пакет) — только упрощённая последовательность locks/state. Это не Tokio scheduler model checking, не исполнение Rust и не производительность.

## Локальное упрощение

Согласованная публикация должна охватывать tuple **messages + history revision + associated context**, а не только завершение durable operation до освобождения run admission.

- Один вариант — clear держит тот же publication/history gate через durable mutation и warm reconciliation. Проверить existing lock order: readers/checkpoints идут history → context → writer; нельзя добавить противоположный writer → history порядок с возможным deadlock.
- Другой — authoritative committed snapshot получает history и revision из одного writer generation, либо warm state публикуется одной структурой со своей согласованной revision. Простая замена reader-а на локальный atomic revision недостаточна: checkpoints, captured tool results и lost ACK уже требуют canonical writer coordination.
- Не заставлять conversation reader брать общий `run_lock`: такой reader нужен hooks/tools внутри active run, который уже владеет run admission. Нужен локальный snapshot-publication boundary, не запрет чтения на всё время turn.
- Не откатывать successful clear и не ослаблять journal validation. No-persistence path должен сохранять тот же snapshot invariant, но его отдельное revision-accounting замечание здесь не считается вторым finding.

Ожидаемое упрощение — один явно проверяемый snapshot contract вместо согласования независимо читаемых компонентов после fact. LOC/RSS/latency не измерены.

## Дедупликация

- PR92 DS-3: dropped direct internal run, accepted append переживает caller, warm reconciliation вообще не выполняется. Здесь clear **уже имеет independent owner**, caller не dropped, операция successful. Один owner из предложенного DS-3 решения сам по себе DS-5 не устраняет; требуется read-publication atomicity.
- PR93 DS-4: disk reader принимает complete **uncommitted** prefix, затем failed append rollback. Здесь mutation committed, rollback отсутствует, mismatch складывает warm history и writer revision.
- Published `runtime-state` RSL-1: background child cards остаются после clear. Не тот payload/read/identity path.
- Published `history-events`: retirement cached display revision без publisher refresh. Здесь не SQLite display cursor/cache lifetime.
- Published `initial-runtime`: callback cancellation и late token cancellation; не successful clear/read.
- В PR84 extracted full text targeted clear/revision/очистка/ревизия сочетания совпадения не дали. Полная повторная дедупликация всех 97 отчётов не заявляется.

Независимый source review выполнен: PASS, source-chain blocker не найден. 13 source hashes записаны автором; illustrative lock model выполнена отдельно от проекта. Rust/HTTP regression остаётся неисполненным. Публикация source-only исследования не означает исправление или runtime-подтверждение.

## Закреплённые source anchors

Пути `core/...` и `app_server/...` относительны `crates/proteus-core/src/`. Ключевые production-файлы не менялись delivery PR87–89.

- [core/runtime.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime.rs#L348-L384)
- [core/runtime/conversation.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/conversation.rs#L36-L55)
