# Proteus: переключение чатов стирает незавершённый commit message Git

## Результат

**P2: подтверждённая потеря draft в настоящем Git+SDK; native GUI-маршрут установлен по исходникам, кликами не проверен.**

Пользователь вводит описание коммита в Git panel чата A, переключается в другой Core-чат B и возвращается в A. Если у A нет отдельного retained Git document, поле уже пустое. Чат A при этом не обязан закрываться, процесс расширения не перезапускается, commit не выполняется. Даже когда оба чата используют один и тот же workspace, черновик теряется.

Неочевидная зависимость: если у A оставлен Git diff/document, **тот же самый** roundtrip сохраняет текст. Документ случайно удерживает весь session instance Git. Это отдельная ошибка lifetime пользовательского draft, не прежний stale-tree action→new-session, не Input echo race и не сброс History другой панелью.

## Версии и метод

2026-11-13, повторная сверка `git ls-remote origin HEAD`:

- Desktop `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.

Сборка из чистого `git archive HEAD`, отдельный Cargo target. Git и SDK не патчились. HTTP fixture на loopback обслуживает синтетические GET; любой POST считается ошибкой. Путь сессии, workspace и текст вымышлены. Настоящие репозитории, файлы пользователя, Core, провайдеры и credentials в опыте не участвуют. Ничего не публиковалось.

## Причинная цепочка

1. [Desktop ensure_panel](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/panels/mod.rs#L64-L82) сохраняет один panel view на всё окно. Его Host динамически следует выбранной root-сессии. Git badge создаётся с [for_command_chat](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/badges/mod.rs#L33-L42), то есть имеет второй динамический context того же процесса.
2. [SessionOpened](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L260-L305) объявляет новый Context, посылает Event и Render для этих поверхностей. Воспроизведение учитывает **оба** context, а не искусственный panel-only runtime.
3. [Git action message](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/main.rs#L196-L196) хранит текст только в `Git.message`. Это поле disposable session instance, без отдельного draft storage.
4. После переключения обоих contexts с A на B, [live_sessions](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/sdk/src/host/scopes.rs#L170-L177) больше не содержит A. [Instances::prune](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/sdk/src/host/instances.rs#L20-L29) удаляет `Git` целиком. Оно вызывается после каждого входящего сообщения из [run](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/sdk/src/host.rs#L828-L839).
5. Возврат A создаёт default instance с пустым message. Возвращается свежий tree с сохранённым action sequence=1, так что это не отброшенный старый reply. [Desktop input update](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/fields.rs#L349-L363) применяет это пустое значение. Отдельного восстановления Git draft в panel entity нет.
6. В положительном контроле `window:space:A` у retained document остаётся на A, поэтому instance не удаляется и draft сохраняется.

## Воспроизведение и контроли

`repro_git_draft.py` запускает настоящий бинарник Git и передаёт NDJSON. Трасса и assertions подтверждают, что Git принял полный многострочный текст и вернул его в input до результатов логического roundtrip. Все сообщения FIFO, без artificial delay и без in-flight action race.

| Сценарий | После проверки |
| --- | --- |
| Повторный Context/Event/Render той же A | Draft сохранён |
| Только command context уходит в B (root panel остаётся A) | Draft сохранён |
| Оба динамических contexts A→B→A, panel первым | **Draft пуст** |
| Оба динамических contexts A→B→A, badge первым | **Draft пуст** |
| Тот же roundtrip, но Git document A остаётся attached | Draft сохранён |

Полные входы, выходы, GET и SHA-256 бинарника лежат в пяти JSON трассах. `draft-observed.log` проверяет наблюдаемое поведение. `--require-fixed` завершается ожидаемым exit 1 на требовании сохранения draft.

## Проверки и ограничения

- Чистая сборка Files+Git: PASS.
- Штатные тесты: **Git 35, Files 24, SDK 51 passed**; doc tests 0.
- Wire: два воспроизведения потери и три положительных контроля PASS.
- Native Desktop/GPUI, focus/undo, real Core, packaging и полный inter-repo suite не запускались. Нельзя утверждать, что проверено восстановление через Ctrl+Z: оно вне этого стенда. Наблюдается потеря SDK draft и выдача пустого значения, а применение в GUI следует из production source.
- Никакой commit, stage, delete, push или другой write endpoint не вызывался. Сохранённые Git-коммиты не затрагиваются; речь только о незавершённом тексте ввода.

## Направление исправления

Отделить маленькие редактируемые drafts от больших disposable caches/session projections. Сохранять draft по явной идентичности session или repository (это продуктовый выбор), с ограничением размера и lifetime, и восстанавливать при возврате. Не отменять `Instances::prune` целиком: так все просмотренные сессии начнут бесконечно удерживать caches/transcript. Регрессия должна проверять оба dynamic contexts, оба порядка переключения, независимость drafts A/B, retained document и его закрытие. Production patch здесь не добавлялся.

## Повтор

```sh
# Чистый Extensions checkout указанного HEAD; отдельный Cargo target.
cargo build --locked -p extension-git
cargo test --locked -p extension-git -p extension-files -p proteus-extension
python3 repro_git_draft.py --binary /path/to/target/debug/git
python3 repro_git_draft.py --binary /path/to/target/debug/git --require-fixed
```

В архив не включены build artifacts и checkout. `source-provenance.json` фиксирует SHA и хеши использованных production source.
