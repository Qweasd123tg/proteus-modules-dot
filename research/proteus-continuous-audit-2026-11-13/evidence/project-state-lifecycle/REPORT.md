# Proteus Desktop: незавершённые операции при переносе окна и выходе Core

Дата: 2026-11-13. Проверенный local/origin HEAD: `75bf201764278eac4b50d156650edcf1429101ff`.

Два новых дефекта жизненного цикла. Старые находки про stale `open_project` catalog и keyboard focus сюда не включены. Production-файлы не изменены, ничего не опубликовано. Native GPUI не запускался.

## PSL-1 [P2]. Выход старого Core оставляет незавершаемый opening ticket и навсегда занятый catalog refresh

### Точная последовательность

1. Workspace посылает `/resume` либо `/sessions` через текущий Core connection 1. Соответственно устанавливается `opening[id]` или `sessions_loading = true`.
2. Собственный backend завершается. `WindowGroup::server_stopped(1)` удаляет shared connection и выставляет `workspace.api = None`.
3. Только после этого UI получает completion старого HTTP job. Он может содержать успешный ответ, прочитанный до выхода, либо ошибку разорванного соединения.
4. `call` / `call_in` обнаруживает, что connection 1 уже не текущий, и делает `return` **до вызова `done` и до error cleanup**.
5. Установка нового connection 2 не снимает старый operation marker. Повторный resume того же чата останавливается на `opening.get(id)`; повторный refresh только ставит `sessions_stale = true`, но нового запроса не запускает.

Наблюдение в probe: после пяти повторов на connection 2 `opening=1, chats=0, requests=1, queued=0`; отдельно для каталога `loading=true, stale=true, requests=1, queued=0`.

Это не перезапись каталога старым содержимым: старый ответ **правильно отвергается**, но забирает с собой единственный путь освобождения операции. Сохранённая сессия не повреждается. Утверждение о бессрочном зависании относится к этому lifecycle без дополнительного cleanup: обычные повторы не помогают. Полный перезапуск клиента или другой путь, явно вызывающий `fail_openings`, может снять opening marker; последнее не исправляет `sessions_loading` само по себе.

### Цепочка исходников

- [Удаление shared connection и per-workspace cleanup](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/windows.rs#L221-L255): `api` сбрасывается, но `opening`, `sessions_loading`, `sessions_stale` не затрагиваются.
- [Guard обычного `call`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace.rs#L373-L400) и [guard `call_in`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace.rs#L425-L452) возвращаются до cleanup callback.
- [`resume_chat`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L178-L218): существующий pending предотвращает новый RPC; ticket снимается лишь внутри пропущенного callback через `pending::take`.
- [`refresh_sessions`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L548-L569): `sessions_loading=false` находится только внутри пропущенного callback.
- [Ленивое получение нового Core](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/drivers.rs#L19-L35) допускает новый backend после опустошения slot; возврат нового подключения не очищает старые markers.

### Проверка и пределы

В probe целиком извлечены production `resume_chat`, `refresh_sessions`, `set_sessions`, `fail_openings`; без изменения control flow извлечены полные UI-result closures `call`, `call_in` и per-workspace closure `server_stopped`. `proteus-tabs` и `pending::take` настоящие. `core-extraction.json` фиксирует диапазоны/хеши.

Core API, shared-connection identity, backend-exit delivery, UI executor и unrelated Workspace services имеют минимальные stand-ins. Probe исполняет заданный порядок завершений, а не реальный Core process crash. Успешный старый ответ непосредственно проверен; равнозначность старой ошибки следует из того, что guard стоит до разбора `value`, но отдельный network-error integration не запускался. Существующие UI callbacks не переизобретены.

Controls: живой connection успешно открывает чат и освобождает ticket; нормальный catalog completion освобождает loading и позволяет второй запрос; `fail_openings` явно снимает pending.

### Направление исправления

Отказ от stale payload не должен означать отказ от завершения принадлежащей ему операции. Привязать operation markers к connection generation и отменять markers именно вышедшего соединения; после восстановления допускать новый resume/refresh. Не удалять безусловно все новые markers из запоздалого старого callback: это создаст обратную гонку. Готовый production patch здесь не заявляется.

## PSL-2 [P2, узкое окно гонки]. Detach ещё загружающегося Codex-чата теряет оба конца открытия

### Точная последовательность

1. Direct Codex driver успешно выполнил `resume`, зарегистрировал route и вернул `Opened`, но исходный Workspace ещё не применил его UI completion. Чат пока показывает loading и не имеет `Chat` entity.
2. Пользователь отделяет эту вкладку в другое окно. `detach_tab` удаляет исходный `opening[id]` и tab. Переносить `Chat` entity ещё нечего.
3. Новое окно вызывает `ensure_chat` и второй `resume` того же thread **до уничтожения первого `Opened`**.
4. Настоящий `CodexService` отклоняет его: `Codex protocol: Codex thread is already open`. Destination callback вызывает `fail_chat_resume`, удаляя новую loading-вкладку.
5. Старый callback также ничего не открывает: `pending::take` уже не находит исходный ticket. Его единственный успешный `Opened` уничтожается. Итог: чат не открыт ни в одном окне; destination получает notice.

Probe держит typed source completion, запускает destination resume, затем доставляет destination completion и source completion. Это один конкретный допустимый порядок, **не утверждение, что любой detach loading-чата обязательно ломается**. Если старый `Opened` уже освобождён до второго resume, конфликта route не будет. Удаления чата или его истории нет; повторное открытие после сброса исходного completion работает.

### Цепочка исходников

- [`detach_tab` удаляет pending и source tab](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/windows.rs#L386-L392), затем [возобновляет незагруженный чат в новом окне](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/windows.rs#L418-L427).
- [`resume_codex`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats/codex.rs#L153-L202) проверяет pending identity и на ошибке вызывает `fail_chat_resume`.
- [CodexService регистрирует route до чтения thread/history](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/agents/codex/mod.rs#L232-L266).
- [Router запрещает повторную регистрацию](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/agents/codex/router.rs#L85-L103).
- [`pending::take`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats/pending.rs#L8-L26) не принимает результат без исходного ticket.

### Проверка и пределы

Настоящие неизменённые `CodexService`, `Router`, `ThreadHandle`, `proteus-codex-client` разговаривают с локальным Python JSONL peer, без аккаунта, сети и модели. Целиком production-методы `resume_codex` и `fail_chat_resume` извлечены в headless Workspace harness. `ChatSpaces`/`TabLayout` настоящие.

Сам `detach_tab` с GPUI window creation **не выполнялся целиком**: narrow adapter повторяет только его операции `opening.remove`, tab extraction и destination `ensure_chat`/resume; его граница явно показана в `probe/src/lib.rs`. Native scheduler, реальный drag/menu detach и вероятность порядка не проверены. Finding означает воспроизводимое межкомпонентное нарушение при указанном interleaving, не native end-to-end подтверждение.

Controls: обычный resume; перенос уже созданного entity без второго resume; повторное открытие после сброса старого completion.

### Направление исправления

Переносить владение одной pending-resume операцией вместе с вкладкой, доставляя её `Opened` текущему владельцу, либо явно запрещать/откладывать detach до завершения загрузки. Нельзя просто удалять старый marker и начинать второй subscription. Готовый production patch не заявляется.

## Результаты и воспроизведение

- Целевые observations/controls: **9 passed**, 3 desired-invariant tests ignored в основном прогоне.
- Полный focused probe, включая доступные исходные тесты Codex и pending: **46 passed, 4 ignored**. Из ignored три новых желаемых инварианта и один уже ignored исходный тест. Это не полный Desktop suite.
- Отдельный `regression_ -- --ignored`: **3 failed, exit 101**, как ожидается на исходном HEAD. Failure означает воспроизведение дефекта, не неудавшийся production patch.
- Независимый self-contained bundle вновь собран с отдельным Cargo target: результат в `standalone.log`.
- Никаких GPUI/portable/full-Core сборок; живой Codex/модель, пользовательские сессии и GUI не использовались.

Из этой папки, с доступным Rust toolchain и кэшем crates.io:

```sh
python3 make_probe.py
python3 make_core_guard.py
CARGO_TARGET_DIR="$PWD/target" cargo test --offline --manifest-path probe/Cargo.toml
# Ожидаемый exit 101:
CARGO_TARGET_DIR="$PWD/target" cargo test --offline --manifest-path probe/Cargo.toml regression_ -- --ignored --nocapture
```

`source/` содержит только необходимые неизменённые исходники Desktop; `source-sha256.json` фиксирует их байты. Архив не является portable-приложением и не содержит build target/cache.
