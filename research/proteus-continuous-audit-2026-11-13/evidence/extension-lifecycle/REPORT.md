# Proteus extension lifecycle: late session and late workspace

Проверено 2026-11-13. Два новых дефекта поздней инициализации. Это **не** ранее описанный `Runtime.error` после off/on, не ошибка SDK polling и не потеря регистрации runtime при rehost.

## HEAD и режим проверки

- Desktop main `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions main `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
- Remote main сверены через `git ls-remote`, исходники для пробы берутся из `git show HEAD`, Extensions для настоящего Context binary взят через `git archive HEAD`.
- Нативное GPUI-окно и Core **не запускались**. Нет утверждения, что весь оконный маршрут проверен кликами.
- Production-код и refs не изменены. Ничего не опубликовано. Все данные и credentials синтетические. Context badge не делает HTTP.

## 1. Scope, созданный до первой выбранной сессии, не получает live session updates

**P2: подтверждённая потеря подписки в production state machine, GUI reachability по исходникам.**

`Host::subscribe_session` проверяет наличие `session_dir` только при регистрации. Если scope создаётся без текущей Core-сессии, он сохраняет `_session_events=None`. Общая подписка HostEvent есть. Когда позднее выбирают/создают Core-чат, SessionOpened запускает процесс и отправляет snapshot, но не создаёт session-подписку. `ensure_scope` при повторном вызове также сразу выходит для существующего context.

Таким образом, начальный snapshot может быть совершенно верным, но последующие изменения config, context usage и transcript metadata не пересылаются. Перерисовка по `NavigationChanged`/`RunSettled` не восстанавливает состояние: она читает старый snapshot. Это именно однократный выбор наличия subscription по временному состоянию, а не ошибка session filtering при доставке.

### Проверка точного кода

`make_probe.py` извлекает неизменённые тела:

- [Host::subscribe_session, 123–140](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/host.rs#L123-L140).
- [Runtime::ensure_scope, 135–202](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L135-L202).
- [Runtime::scope_event, 236–305](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L236-L305).

Вокруг них инертные typed GPUI entities и event bus. `subscribe` действительно сохраняет production callback, а тест затем передаёт ему синтетический `SessionChanged`; старт процесса только считается, не имитируется как настоящий.

Результаты:

1. Attach без session: есть общая подписка, session subscription отсутствует.
2. Появление session + SessionOpened + повторный ensure_scope + NavigationChanged + ContextChanged: session subscription всё ещё отсутствует.
3. Emit `SessionChanged` нужной сессии: ни одного SessionUpdate.
4. Контроль attach с уже выбранной session: matching SessionChanged пересылается, чужая session отфильтровывается.
5. Контроль пересоздания scope после появления session: subscription существует.
6. Preview не подписывается на production events.

### Проверка последствия настоящим пакетом

Неизменённый Context+SDK binary собран в новом Cargo target. `context_wire.py` отдельно проигрывает сообщения, оставшиеся после потерянного forwarding: snapshot 10%, render, NavigationChanged, RunSettled. Последовательность настоящих badge replies: **10 → 10 → 10**. Контроль отправляет обычный SessionUpdate с 80%: **80 → 80** на следующей навигации. Это подтверждает потребителя и достаточность пропущенного сообщения, но **не** превращает probe в интеграционный тест всего native Desktop/Core.

Полный wire: `context-wire.json`; поле `native_desktop_run=false` явно сохранено.

### Штатный маршрут, подтверждённый исходниками

Детерминированный кандидат для native regression:

1. Отделить **только Terminal** в новое окно. [detach_tab](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/windows.rs#L344-L436) создаёт ready Workspace и переносит документ. Chat entity не переносится для document id. Terminal runtime не является runtime пакетов Context/Mode.
2. В новом окне пока нет command chat: [active_chat_key](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L27-L39). При этом root остаётся Core, поэтому [core_context](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/drivers.rs#L37-L39) допускает badges; [sync_badges](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/badges/mod.rs#L19-L46) создаёт их с `for_command_chat()`.
3. Дать новому окну отрисоваться, затем создать в нём новый Core-чат. Динамический command context остаётся прежним; SessionOpened не заменяет scope.
4. Убедиться, что новый run меняет context usage. Ожидаемый дефект: Context badge остаётся на первом snapshot; input/runtime самого агента не перестаёт работать.

Этот маршрут не утверждается как уже воспроизведённый в живом GUI. Наличие scope без сессии и отсутствие восстановления доказаны ниже native UI, по точному control flow. В отличие от rehost-registry finding, у Context в этом сценарии собственный новый runtime, не принесённый Terminal.

### Исправление-кандидат

Подписывать workspace lifetime независимо от **текущего** `supports_core`; имеющийся callback уже проверяет актуальный session_dir при доставке. Альтернатива: явно достраивать отсутствующую подписку при первом SessionOpened. Preview/Settings должны оставаться изолированными. `candidate-late-context.patch` реализует первый вариант как исследовательский кандидат, не production-правку.

## 2. Появление workspace metadata не возобновляет ожидающий launch

**P3: подтверждённый missing retry при заданном состоянии; GUI timing route не выполнен.**

Предусловие: живой scope/view создан, но его `Host::workspace_path` ещё `None`. Это предусмотренное production-состояние для `for_space` документа, пока нет metadata именно его root. [Host::workspace_path](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/host.rs#L295-L320) не подставляет соседний проект. [Runtime::launch](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime.rs#L242-L263) правильно не запускает процесс без workspace.

Но по приходу metadata обрабатывается ContextChanged. Его ветка немедленно возвращает управление, если `process.is_none()`. Поэтому событие, делающее connection готовым, не вызывает повторный start. Общий путь start ниже этой ветки недостижим. Runtime остаётся без процесса и без ошибки до другого события, новой поверхности или явного Restart.

Точная `scope_event` в probe: первая попытка start=1 при отсутствующем workspace; устанавливаем folder и посылаем ContextChanged: **start всё ещё 1, сообщений 0**. Контроль NavigationChanged: start становится 2. При уже живом процессе обновление metadata корректно отправляет Context+NavigationChanged, без нового start. При `Runtime.error` кандидат также не делает автоматический retry.

### Reachability и существенное ограничение

В [startup](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/startup.rs#L230-L252) metadata **активного** восстановленного owner заранее подготавливается. Поэтому нельзя утверждать, что обычный restart со всеми открытыми Terminal воспроизводит проблему.

Потенциально достижимая последовательность: после запуска выбрать ещё не возобновлённую сохранённую область с Terminal до получения `/sessions` metadata. [open_chat](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L111-L150) восстанавливает её layout, но resume выполняется асинхронно. В это время [ensure_document](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/tabs/mod.rs#L64-L93) может создать Terminal scope с неизвестным folder. Завершение resume устанавливает session_projects и вызывает [finish_chat_resume](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L262-L289), который emits ContextChanged. Здесь требуется controlled-delay native test; частоту в реальном UI этим исследованием не измеряли.

Кандидат: на ContextChanged при отсутствующем процессе и отсутствии runtime error вызвать start и вернуться; для уже живого процесса оставить существующую metadata-only логику. Это не перезапуск процесса на каждую metadata update.

## Итог проверок

- Exact-source probe текущего HEAD: **7 passed**, 2 desired invariants ignored в обычном запуске.
- Отдельный desired run: **2 FAILED**, exit101, именно по отсутствию подписки и retry.
- Candidate на том же harness: **2 desired + 5 controls passed**.
- Неизменённые Extensions: Context target **3 passed**, SDK **51 passed**, doc tests 0; реальный Context wire **PASS**.
- `git apply --check candidate-late-context.patch`: PASS.
- Полный Desktop test suite, нативная подписка GPUI, оконный manager, реальный Core и portable не проверены. Candidate **не готов к merge** без них.

## Воспроизведение

```sh
python3 make_probe.py /path/to/Proteus-desktop
rustc --edition 2024 --test lifecycle_probe.rs -o lifecycle_probe
./lifecycle_probe --nocapture
./lifecycle_probe --ignored --nocapture # ожидаемо exit101 на pinned HEAD
rustc --edition 2024 --test candidate_probe.rs -o candidate_probe
./candidate_probe --ignored --nocapture
./candidate_probe control --nocapture

# Чистый Extensions checkout указанной ревизии:
cargo build --locked -p extension-context
cargo test --locked -p extension-context -p proteus-extension
python3 /path/to/evidence/context_wire.py --binary target/debug/context
```

`source-extractions.json` содержит SHA/диапазоны точных методов. `source-provenance.json` содержит hashes неизменённого SDK/Context исходника и построенного binary. В archive нет target или исходников всего репозитория.
