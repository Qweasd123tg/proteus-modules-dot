# История, события и UI: coherence ревизий

Дата: 2026-11-13. Core `89997df995df7c39b713e16aba216ecb19c8f497`, Desktop `75bf201764278eac4b50d156650edcf1429101ff`.

Production не изменён. Изолированная рабочая копия Core: `/workspace/shared/history-events-audit`. Добавлены только два audit tests в существующий `app_server/events/tests/active_followup.rs`. Публикаций, production запусков и платных model calls не было.

## Подтверждено: сервер публикует курсор истории дольше, чем хранит соответствующую ревизию

Общий корень: immutable revision у клиента и `AppEventPublisher` не управляет временем жизни единственного SQLite display projection. Другой projector заменяет cache, но не каждый такой переход доставляет новый snapshot читателю.

### A. Переход к queued follow-up делает старую историю недоступной подключённому клиенту

1. Возобновлён сохранённый разговор со 120 строками. Начальный `history.before=70`.
2. Первый root turn остаётся активным. Страница по старому курсору читается: total=120.
3. Пользователь ставит следующий запрос в очередь. Первый turn завершается, начинается второй; второй специально удерживается deterministic barrier.
4. `RuntimeEventSink` перестраивает completed projection и устанавливает его вместе с новым `TurnStarted`. Уже открытая subscription получает runtime events, но **ни одного нового SessionSnapshot**.
5. Page read со старым revision теперь выдаёт `history revision changed; refresh the session snapshot`.
6. Новая subscription получает новый before=72; по новому курсору страница читается: total=122.

Production границы:
- `crates/proteus-core/src/app_server/events/session.rs:260-299`: new root-turn boundary вызывает `completed_transcript`, затем `send_with_history`, но не `publish_snapshot`.
- `crates/proteus-core/src/core/session_store/read_model/sqlite.rs:151-185`: страница относится к единственной сохранённой projection revision.
- Desktop `src/ui/chat/history.rs:627-661`: failed page только показывает ошибку; нового snapshot не запрашивает.
- Desktop `src/ui/chat/turn_copy.rs:226-266`: Copy whole response обращается к той же pinned revision, поэтому при переходе через границу resident page тоже получает ошибку.

Эффект: старые страницы/seek и требующее старых страниц копирование ломаются до терминального snapshot всей очереди либо reconnect. Не теряются canonical messages; уже resident rows остаются видны. Условие: сохранённая история выходит за пределы live tail и follow-up остаётся активным. Обычные single-turn и reconnect regression tests сами по себе этого не ловят.

Evidence: `queued-cursor.log`, `active-followup-target.log`; тест `audit_connected_followup_reader_keeps_retired_history_revision`.

### B. Latest history-page read может сломать даже новую subscription и /history активной сессии

1. Та же сохранённая история 120 строк и первый активный turn.
2. Чтение страницы по старому курсору успешно.
3. Другой reader запрашивает latest page без revision. Выполнен точный production read-model path, который вызывает публичный `/history/page` handler: `transcript_page(&store, None, None)`.
4. Источник уже содержит durable user input. Latest read успешно перестраивает общий cache, возвращает total=121 и другую revision.
5. Старый cursor больше не читается.
6. Publisher не знает об этом rebuild: даже **новая subscription возвращает старую retired revision**.
7. Вызов настоящего `server.transcript()` тоже завершается `history revision changed; refresh the session snapshot`. Это путь активного `/history`.

Production границы:
- `crates/proteus-core/src/app_server/http/sessions.rs:232-251`: latest history-page читает SessionStore без участия active AppServer state.
- `crates/proteus-core/src/app_server/read_model.rs:66-117`: unversioned miss перестраивает read model и записывает новую projection.
- `crates/proteus-core/src/app_server.rs:315-334`: full transcript использует revision из оставшегося прежним publisher snapshot.

Эффект: ordinary read-only API call может инвалидировать читаемость истории уже активной сессии. Reconnect в этом варианте не лечит, нужен следующий genuine publisher refresh/turn settlement. Условие: другая latest-page read того же активного session_dir; автоматический trigger через каждый обычный UI gesture НЕ утверждается. Public endpoint behavior и active publisher доказаны напрямую, реальный HTTP сокет и окно GPUI в этом проходе не запускались.

Evidence: `latest-reader-cursor.log`, `active-followup-target.log`; тест `audit_latest_history_read_retires_active_snapshot_without_notification`.

## Направление исправления, не реализовано

Нужен единый инвариант: опубликованная revision должна оставаться читаемой, либо её замена должна согласованно продвинуть snapshot читателей. Для A минимальный путь: при install нового completed prefix на queued boundary опубликовать snapshot с новым cursor; сохранить atomic ordering с TurnStarted и последующими deltas. Для B нужно отдельно согласовать unversioned read rebuild с active server либо хранить адресуемую предыдущую projection пока на неё ссылается publisher. Просто принудительный reconnect клиента недостаточен для B.

## Проверки и отрицательные результаты

- Весь `app_server::events::tests::active_followup`: **4/4 passed**, включая два прежних и два audit tests. Audit tests намеренно подтверждают наблюдаемое плохое поведение; это не passing regression для желаемого поведения.
- Desktop production-source `SessionCursor`, `PendingCursor`, `ContextRequests`: **5/5 passed**. Отдельный маленький probe импортирует исходники через `#[path]`; Core contracts локального SHA. GPUI не подменялся тестом UI.
- `git diff --check`: clean.
- Прочитаны границы SSE subscribe/resync, client transport/pump, history paging/seek/merge, readonly saved documents, copy, session feedback/config/context fencing.
- Гипотеза early terminal child notification → stale readonly tail **не подтверждена**: соседняя проверка установила штатный commit-before-SubagentFinished порядок.
- Наличие разных delta-offset folds само по себе не объявлено багом: штатный producer делает contiguous offsets; достижимый нарушающий сценарий не показан.

Ограничения: это focused isolated functional audit, не полный workspace gate, не real-provider dogfood и не GUI proof. Для Core использован direct cargo lib target с synthetic registered workflow; общий scripts/test.py дополнительно готовит production module artifacts, которые этим tests не требуются. Во второй проверке production endpoint read-model функция и AppServer вызываются непосредственно, без HTTP serialization/socket. Источник/данные только synthetic temporary sessions, сетевых provider вызовов нет.
