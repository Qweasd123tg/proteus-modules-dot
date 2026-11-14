# Третий проход: reconnect receipts и перенос вопроса между окнами

2026-11-13. Сверены удалённые HEAD: Core `89997df995df7c39b713e16aba216ecb19c8f497`, Desktop `75bf201764278eac4b50d156650edcf1429101ff`, изменений нет. Production не менялся, публикаций нет.

## Подтверждено: accepted queued receipt остаётся после выполнения, если его user row вышла из bounded tail

Это не прежняя ошибка корреляции одинаковых параллельных текстов: здесь один queued request, его HTTP acceptance достоверно успешен, message_id известен, текст уникален.

Реальный isolated Core AppServer + неизменённый Desktop Feedback, импортированный напрямую через `#[path]`:
1. Первый root run активен, id=`initial-run`.
2. Клиент начинает отправку `queued-request` с текстом `queued payload`.
3. Настоящий `dispatch_user_message` возвращает `SendDispatch::Queued` с message_id. Клиент получает успешный HTTP-equivalent receipt и вызывает `Feedback.complete(..., true, Some(id))`.
4. Клиент не наблюдает stream во время выполнения. После первого хода queued follow-up сохраняет 60 отдельных assistant messages.
5. Новая subscription получает корректный terminal snapshot: последние 50 сообщений, без queued user row. `execution.last.run_id` по действующему run-registry остаётся `initial-run`, а не локальным id queued request.
6. Применение действующего `Feedback.snapshot` и пустой актуальной queue оставляет **один visible send receipt со статусом «Отправлено»**.
7. Контроль с явным предоставлением старого message_id в snapshot очищает receipt, то есть блокер именно в недоступной корреляции.

Evidence:
`AUDIT: completed_queued_user_is_outside_tail=true live_rows=50 last_run=initial-run stale_receipt=1 status=Отправлено`.

Причина:
- `src/ui/chat/feedback/mod.rs:72-79` хранит принятый, но ещё не observed send.
- `:120-140` принимает только совпадение run id либо message id в bounded snapshot.
- `src/ui/chat/session.rs:146-157` передаёт только IDs live snapshot, не archived history.
- `Feedback.queued([])` не удаляет accepted records; history-page loading также не обновляет Feedback.
- queued follow-ups по контракту выполняются под первоначальным app-server run id.

Эффект ограниченный: stale/дублирующий footer receipt и удержание transient send state. **Нет доказанного повторного исполнения, потери сообщения или ложной отправки.** Пользователь видит «Отправлено», не «Отправляю». Обычно не проявляется, когда хотя бы один queue/echo event был наблюдён либо user row ещё помещается в 50-row tail.

Направление исправления: acceptance/queue reconciliation не должна требовать присутствия уже исполненного input в resident transcript. Нужен подтверждённый post-acceptance baseline/ack correlation, а не text matching и не неограниченная загрузка всей истории. Не следует просто считать любую старую пустую queue доказательством окончания нового send без ordering fence.

Evidence: `queued-receipt-tail.log`, `active-followup-feedback-target.log`, test `audit_accepted_queued_receipt_survives_reconnect_after_user_row_leaves_tail`.

Полный затронутый тестовый модуль после добавления cross-repo import: **15/15 passed**, включая 10 существующих Desktop Feedback tests, два существующих Core follow-up tests и три audit observations. Это observation tests, не проверка исправленной production реализации.

## Подтверждён структурный пробел, GUI-эффект ещё требует проверки: Core question input не rehost-ится

- `src/ui/chat/user_input.rs:81-107` один раз создаёт InputState и `subscribe_in(window)` для free-text question; PressEnter callback вызывает `next_question` с этим Window.
- Повторный вызов использует `or_insert_with`: существующие entity/subscription возвращаются без перепривязки.
- `src/ui/chat/mod.rs:384-407`, `Chat::rehost`, переносит composer, composer subscriptions, reply views, Codex answer inputs и scroller. `UserInputDrafts.texts` не затрагивается.
- Vendored `vendor/gpui-base/src/input/base/state.rs:1067-1106` явно хранит Window-specific focus/blur/activation subscriptions и заменяет их только при `InputState::rehost`.

Exact-method instrumentation: после перехода window1→window2 Chat/composer/Codex-answer получили window2; Core answer input и его Enter subscription остались window1. Текст не был потерян.

**Что доказано:** omission в реальном Chat::rehost и отсутствие lazy rebind в question renderer. **Что не доказано в живом GPUI:** точный симптом Enter/focus/cursor после переноса и закрытия исходного окна. Не называть это уже воспроизведённой GUI-поломкой.

Следующая ручная/GPUI integration проверка: открыть Core request_user_input, набрать free-text, вынести chat tab в новое окно, закрыть исходное, проверить текст/undo/focus/Enter. Исправление должно rehost-ить InputState и заново привязать subscribe_in, сохраняя текст и ответы.

Evidence: `make_rehost_probe.py`, `rehost-probe.rs`, `rehost-omission.log`, `rehost-extraction.txt`. **1/1 instrumentation test passed**, но GPUI Entity/Context/InputState methods здесь stubs, не настоящий runtime.

## Ограничения и состояние

- Реальные persisted temporary Core sessions и runtime queue, synthetic registered workflow, без моделей/платных API.
- HTTP acceptance представлен настоящим return value server dispatch; сетевой HTTP/SSE транспорт не запускался. Snapshot берётся через реальную AppSubscription.
- Desktop Feedback импортирован целиком без изменений. GUI window/footer не рендерился.
- `all-audit-tests.patch` содержит все Core audit tests и absolute local `#[path]` к Desktop Feedback: это воспроизводимый локальный audit материал, **не готовый переносимый PR patch**.
- `repro-tests.patch` оставлен первоначальным отдельным evidence двух revision-coherence tests.
- `git diff --check` чистый. Никаких production commits/push/merge.
