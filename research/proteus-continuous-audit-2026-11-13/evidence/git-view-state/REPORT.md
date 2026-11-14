# Proteus: согласованность состояния Git UI между views и hash aliases

Проверено 2026-11-13. Два новых дефекта подтверждены настоящим неизменённым процессом `extension-git` с настоящим SDK, NDJSON stdin/stdout и синтетическим loopback HTTP API. Нативное окно GPUI не запускалось: вывод о том, что пользователь остаётся на History, дополнительно основан на исходниках Desktop. Никаких Git write endpoints, настоящих репозиториев, сессий или credentials в сценариях нет.

## Revisions и границы

- Desktop HEAD и remote main: `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions HEAD и remote main: `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
- Точные проверки: `verified-heads.txt`.
- Штатный `cargo test --locked --offline -p extension-git`: **35 passed**, лог `git-baseline.log`.
- Бинарник собран из текущих production Git/SDK sources с отдельным Cargo target. `git diff` подтверждает отсутствие изменений production sources. В исходном Extensions checkout уже были чужие audit-добавления только к `sdk/src/host/tests.rs`; обычный бинарник и этот package test target их не включают.
- Исправления, commit, push, PR не выполнялись. Все добавленные здесь файлы только в audit-каталоге.

## 1. P2: другая Git-панель оставляет History первой панели на постоянной загрузке

**Условия:** две поверхности Git panel одной сессии в общем runtime. Панель A открыта на History, B открывается заново либо переключается на Changes. Обычный путь к общему runtime по Desktop sources: перенести Git document из A в другое окно, затем открыть Git panel в окне назначения. `rehost_runtime` регистрирует прежний процесс там. Два независимо запущенных окна без такого общего runtime этим repro не покрываются.

**Воспроизведение (`repro_git_views.py`):**
1. Render `panel-a`, затем настоящий action `tab=1`. В History возвращается `list` с одним синтетическим коммитом.
2. Render Git commit document в A, создать второй context того же session_dir, отправить настоящий SDK `rehost` этого document в B, затем render `panel-b`.
3. На следующем `navigation_changed` панель A получает вместо list только `loading("Загрузка истории…")`. Её action sequence остаётся 1: это допустимый свежий ответ, а не отфильтрованное старое сообщение.
4. Явный `refresh` панели A с sequence=2 снова возвращает loading.
5. Changes→History в A восстанавливает list. Контроль с единственной панелью сохраняет list при повторном render, event и refresh.
6. Отдельный вариант: после открытия B переключить её History→Changes. A снова теряет list.

Трасса A: `initial loading → list → loading → refresh/loading → Changes/loading → History/list`.

**Причина:** `Git.tab` один на процесс; новый panel сбрасывает его в 0, любой `tab` action меняет его для всех. `history_tab` отдаёт loading при `self.tab != 1`. Но выбранный таб Desktop находится в отдельной `DeclarativeView.tabs`. Получение нового root не меняет это локальное значение. Повторный клик уже выбранного History также не отправляет action из-за `!active` guard.

Исходники:
- [Git: новый panel сбрасывает общий tab](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/main.rs#L142-L149)
- [Git: общий обработчик tab](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/main.rs#L188-L189)
- [History gating](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/panel.rs#L403-L410)
- [Desktop: локально выбранная вкладка](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/layout.rs#L90-L95), [action только при !active](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/layout.rs#L145-L160)
- [Desktop: повторное использование runtime и перенос в другое окно](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/mod.rs#L204-L247)
- [SDK: addressed action обновляет sibling views](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/sdk/src/host.rs#L559-L573)

**Направление исправления:** хранить active tab per view, очищать запись в `closed`, передавать view при построении panel/history; данные log/cache можно оставить общими. Не убирать ленивую загрузку истории ради обхода дефекта. Регрессия обязана держать две панели с разными локальными tab selections.

`observed.log`: все 5 групп проверок проходят. `--require-fixed`: **exit 1**, требуемая регрессия «History A survives B render» красная. Транскрипты: `single-panel-control.json`, `second-panel-repro.json`, `sibling-tab-repro.json`.

## 2. P3: штатный shortcut последнего коммита ломает сворачивание папок в Graph

**Воспроизведение (`repro_git_hash_identity.py`):**
1. Настоящий panel root содержит кнопку `open_commit` с value `abc1234`. Тест проверяет именно value выданной кнопки.
2. Выполнить её action, отрисовать запрошенный document `Коммит abc1234`, затем открыть штатный Graph.
3. API вернул тот же коммит под полным hash `abc1234000000000000000000000000000000000`, единственный файл `src/a.rs`.
4. Tree содержит `dir:src`, expanded=true. Action `detail_file` с `{id:"dir:src", event:"collapse"}` оставляет expanded=true и `src/a.rs` видимым.
5. Выбрать тот же коммит через `graph_log` с его полным row id. Тот же collapse теперь даёт expanded=false и убирает дочернюю строку; expand также работает.

**Причина:** shortcut передаёт short hash и `open_commit` сохраняет его в `self.commit` без нормализации. `detail_file` записывает закрытую папку под `short_hash:src`, а `commit_inspector → files_in` читает `full_hash:src` из API commit. Тот же mismatch оставляет все graph rows `selected=false`, хотя справа показан инспектор выбранного коммита. Это один дефект идентичности, а не два независимых findings.

Это **не ранее найденная коллизия `dir:` с именем файла**: fixture использует обычный `src/a.rs`, и штатная директория `dir:src` работает сразу после выбора full hash.

Исходники:
- [Shortcut отдаёт short](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/panel.rs#L500-L512)
- [open_commit сохраняет raw hash](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/main.rs#L317-L322)
- [Чтение состояния по full hash](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/details.rs#L123-L135), [folder key lookup](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/details.rs#L30-L35)
- [Запись состояния по self.commit](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/details.rs#L185-L200)
- [Точное сравнение graph selection](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/history.rs#L75-L98)

**Направление исправления:** привести выбранный коммит и ключи UI-состояния к одной canonical identity после разрешения commit response. Короткий hash можно оставить для подписи document, но не смешивать его с полным ключом. Добавить shortcut→Graph→collapse регрессию и контроль full-hash selection.

`hash-observed.log`: наблюдение и 2 положительных контроля проходят. `--require-fixed`: **exit 1**, требуемая регрессия collapse после shortcut красная. Полная трасса `short-hash-repro.json`.

## Дополнительное покрытие и ограничения

Прочитаны retained field/event adapters, общий list/lanes/tree routing, picker options/filter, tabs/disclosures, prompts/menus, rich text/content slots, document retargeting; Git panel/history/details/documents, SDK scope/render dispatch. Это углублённый проход по выбранным взаимодействиям, не новое заявление о полном построчном чтении всех репозиториев.

Повторно не учитывались прежние Input echo/lines, Steps, Git keyboard, stale callback family Graph/Tree/List, `dir:` filename collision. Изменяемый `Code.wrap` остаётся кандидатом: текущий `prepare_fields` не переустанавливает soft_wrap у retained Editor, но надёжный штатный сценарий изменения этого флага здесь не подтверждён, поэтому finding не заявлен.

Проверены wire-ответы и исходники потребителя. Нет замеров GUI latency/RSS, click geometry, живого desktop сценария или полного inter-repo release gate. Loopback заменяет серверные ответы, но Git и SDK не заменены заглушками.

## Повторный запуск

```sh
source /workspace/shared/proteus-toolchain/env.sh
CARGO_TARGET_DIR="$PWD/desktop-behaviour/audit-ui-view-state/extension-target" \
  cargo build --locked --offline --manifest-path protocol-extensions/Cargo.toml -p extension-git
python3 -B desktop-behaviour/audit-ui-view-state/repro_git_views.py
python3 -B desktop-behaviour/audit-ui-view-state/repro_git_hash_identity.py
# Desired regressions, expected exit 1 on pinned sources:
python3 -B desktop-behaviour/audit-ui-view-state/repro_git_views.py --require-fixed
python3 -B desktop-behaviour/audit-ui-view-state/repro_git_hash_identity.py --require-fixed
```
