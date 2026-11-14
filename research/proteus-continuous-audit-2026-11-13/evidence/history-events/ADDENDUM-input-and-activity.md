# Следующий проход: typed input и sidebar activity

2026-11-13. Повторный `ls-remote origin refs/heads/main` подтвердил неизменные Core `89997df995df7c39b713e16aba216ecb19c8f497` и Desktop `75bf201764278eac4b50d156650edcf1429101ff`.

Ни production, ни репозитории назначения, ни реальные сессии не изменялись. Все новые файлы только в evidence-каталоге. Предыдущий revision/cache defect не повторяется в этом отчёте.

## 1. Два вопроса с одинаковым question id незаметно превращаются в один ответ

Это **не** прежний collision request_id между child agents. Здесь один корректно адресованный request, два разных вопроса внутри него.

Вход:
- id=choice, header=Language, question=Which language?, options=Rust/Python;
- id=choice, header=Database, question=Which database?, options=SQLite/Postgres.

Production parser принимает оба вопроса: `normalize_questions` валидирует количество/заголовок/текст/options, но не уникальность итоговых ids (`crates/proteus-core/src/tools/request_user_input.rs:250-307`).

Desktop использует этот id как идентичность черновика, а не индекс вопроса:
- `src/ui/chat/user_input.rs:54-67`: выбранные ответы лежат по request_id → question_id;
- `:113-143`: answered и финальная response берутся из этого shared state, response собирается в HashMap по question_id.

Наблюдение из исполняемого exact-source probe:
1. После выбора Rust в первом вопросе второй уже `is_answered=true`, хотя ни SQLite, ни Postgres не выбирались.
2. Выбор SQLite во втором вопросе заменяет ответ Rust первого.
3. Финальный payload: `{"answers":{"choice":{"answers":["SQLite"]}}}`. Два отдельных выбора сохранить невозможно.
4. Контроль с id=language и id=database сохраняет оба ответа независимо.

Практический эффект: ошибочная, но принимаемая модельная tool invocation может изменить смысл пользовательских ответов и передать модели неполный результат вместо понятной validation error.

Направление исправления: отвергать duplicate итоговые question ids до отправки user-input request. Проверять уже после fallback id к question text, чтобы покрыть явный id и совпадающий fallback. Автоматически переименовывать ids не требуется и может менять mapping, ожидаемый вызывающим tool.

Evidence: `input-duplicate-ids.log`, `make_input_probe.py`, `input-probe/`, `input-extraction.txt`. **2/2 tests passed** (bad-case observation + distinct-id control).

Ограничение: production parser/DTO и pure UI state helpers извлечены дословно, два GPUI construction/mutation метода не включены; Context/Entity read заменены минимальными stubs. Тест использует только option selections, без free-text и rendering. Полный GUI, actual model generation и сетевой вызов tool не выполнялись. Частота выдачи duplicate ids реальными моделями не измерялась.

## 2. Задержавшийся /sessions ответ перезаписывает более свежую SSE activity

Сценарий обычной асинхронной гонки, без потери событий:
1. В workspace есть background session с activity Running, pending_user_inputs=0.
2. Начинается refresh_sessions. HTTP ответ уже отражает это состояние, но callback ещё не исполнен.
3. Через активный chat stream приходит SessionActivityUpdated той же background session: WaitingInput, pending_user_inputs=1. Activity handler корректно записывает его в summary.
4. Приходит прежний HTTP callback. `session_catalog_epoch` не изменился, потому что Activity handler его не продвигает. `set_sessions` заменяет summaries целиком.
5. Summary возвращается к Running/0. `sessions_stale=false`, дополнительный refresh не назначен.

Причинные границы:
- Core `app_server/http/sessions.rs:35-44` добавляет снимок activity в ответ /sessions.
- Desktop `src/ui/chats.rs:507-525` применяет SSE activity, но не защищает её от pending list response.
- `:549-599` проверяет только catalog epoch, используемый для lifecycle/delete, и не activity freshness.
- `:535-546` целиком заменяет Proteus summaries.

Evidence exact production-method probe:
`AUDIT: SSE waiting_input/1 → delayed HTTP running/0; calls=1 pending_refresh=false`.
Контроль HTTP response → SSE оставляет WaitingInput.

Эффект: sidebar/summary может перестать показывать, что агент ждёт ответа, и оставаться устаревшим до следующего activity/list refresh или переключения. **Сам pending request не теряется**, ответить в открытом чате можно. **System attention notification не объявляется потерянным:** `Tracker::baseline` не перезаписывает ранее наблюдавшийся статус, это отдельно проверено существующим production test.

Направление исправления: request-generation fencing либо merge, сохраняющий per-session activity, полученную после начала соответствующего list request; как минимум пометить catalog stale при новом Activity во время loading и не выдавать старый activity за актуальный. Точный дизайн оставлен реализации, production не менялся.

Evidence: `activity-race.log`, `make_activity_probe.py`, `activity-probe/`, `activity-extraction.txt`. **3/3 tests passed** (bad-order observation, normal-order control, production attention regression).

Ограничение: полные `refresh_sessions`/`set_sessions` и Activity match-arm извлечены дословно; callback поставлен в очередь stub transport и завершён управляемо. Реальные tabs/attention modules и DTO, но GPUI Context notifications/rendering и actual HTTP socket не выполнялись. Это доказательство state race, не скриншот и не замер частоты.

## Не объявлено находками

- `is_other` не проверяется Desktop renderer, но native Core tool сам выставляет Other=true; стандартный нарушающий путь не доказан.
- Reused request id across reconnect мог бы сохранить UI draft, но это требует отдельной проверки producer identity guarantees; не смешивать с уже известной simultaneous child collision.
- Activity broadcast overflow может требовать отдельной reconciliation, но реальный достижимый missing-background-update сценарий в этом проходе не воспроизведён.
