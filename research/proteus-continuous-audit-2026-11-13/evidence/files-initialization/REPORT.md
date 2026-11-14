# Files / SDK: document-only initialization and active-document refresh

Проверено 2026-11-13. Новые результаты, **не повтор** rename retarget, diff-mode reset или registry rehost.

Origin HEAD повторно сверены непосредственно в этом проходе:

- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`

Из `git archive HEAD` создана чистая отдельная копия Extensions. Production sources не менялись. Files и SDK собраны заново в собственный Cargo target; тесты используют реальный process/stdin/stdout JSON Lines и синтетический in-memory HTTP API на loopback. Нет реальных проектов, аккаунтов или Core provider calls. Ничего не опубликовано.

## 1. P2: после запуска/restart процесс не получает активный документ, поэтому Files poll сохраняет устаревший текст

### Подтверждённое wire-поведение

Передали штатную стартовую последовательность `hello → context → render(document)` для `src/remote.rs`. После первого чтения API изменили fixture с `remote fixture` на `external change fixture`.

- Настоящий таймер SDK сработал два раза через 5 секунд. Обе реальные outgoing view сохранили **старый текст**.
- За 10 секунд сервер получил только **один** `/workspace/file`: начальную загрузку.
- Затем передали `navigation_changed` с тем же текущим документом. Следующий view сразу получил новый текст, API reads стало 2.
- Контроль отличается только наличием `navigation_changed` перед изменением fixture: первый штатный poll через 5 секунд уже показывает новый текст, reads=2.

Ни таймер, ни HTTP не замоканы. Время не ускоряли. В `active-missing-repro.json`, `active-announced-control.json` сохранены входные/выходные сообщения и API calls. Desired regression (`--require-fixed`) красный по содержимому, а не из-за сборки или timeout.

### Сквозная причина и достижимость

Files проверяет возраст cached preview **только** если `host.active_document == path`:
[Files body, L56–82](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/document.rs#L56-L82).

SDK заполняет active_document только из `event.document`, не из `context`, `render` или snapshot. Поэтому наличие открытого отображаемого документа само по себе не делает его active для refresh.

Desktop при запуске шлёт `Hello`, затем `announce_scope`, затем render существующих поверхностей:
[Runtime launch, L260–295](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime.rs#L260-L295).
`announce_scope` отправляет Context и, если пакет запросил, snapshot. **Текущий active document он не посылает**:
[announce_scope, L206–233](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L206-L233).

Самый прямой штатный маршрут: document уже открыт и активен, процесс расширения перезапущен/reloaded, пользователь не переключал вкладку после перезапуска. Restart вызывает stop/start, сохраняя attached views; восстановительный launch отправляет указанную последовательность, но не navigation state. Пока нет нового navigation/session-open/run-settled, Files ошибочно считает видимый документ скрытым. Переход назад на вкладку скрывает проблему, поскольку приносит недостающее событие.

Также первый navigation до deferred launch не буферизуется: `send` при `process=None` ничего не делает. [send/restart, L157–170](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime.rs#L157-L170), [scope_event, L278–288](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L278-L288).

**Граница доказательства:** последствия startup messages проверены реальным Files+SDK бинарником. Достижимость через Desktop launch/restart проверена по production-коду, а не нативным GPUI-кликом. Полный startup UI/OS-watchers в этом проходе не запускались. Отдельный rehost-specific случай **не объявлен подтверждённым**: подписка и NavigationChanged зависят от очередности GPUI defer/effects.

### Направление исправления

После объявления каждой production scope передавать актуальный navigation state (включая active document) до/вместе с первым render, в том числе после restart/reload. Не превращать все retained документы в active: это ломает намеренно ленивое обновление скрытых вкладок. Добавить host+SDK regression на восстановление активного документа без последующего переключения вкладок.

## 2. P3: «Копировать путь» в document-only runtime зависит от открытия соседней Files panel

### Подтверждённое поведение

У context уже есть `/fixture/project`, `/sessions/current` готов вернуть правильную абсолютную папку.

1. Открыли только документ `src/remote.rs`, не панель Files.
2. Кнопка документа имеет value `src/remote.rs`; реальное действие `copy` отправляет clipboard с **относительным** `src/remote.rs`.
3. В том же процессе открыли Files panel в **другом контексте той же сессии**.
4. Тот же документ, та же кнопка без изменения файла теперь возвращает `/fixture/project/src/remote.rs`.
5. API metadata requests до панели=0, после=1. Содержимое документа не изменилось.

Это зависимость корректности действия одной поверхности от побочного создания другой, а не сбой метаданных API. `copy-path.json` сохраняет сам исходящий clipboard protocol, не только предположенный button value.

### Причина и достижимость

- `render(Document)` не вызывает metadata refresh; `render(Panel)` вызывает: [Files main L111–119](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/main.rs#L111-L119).
- `cwd` впервые устанавливается в `refresh`, через `/sessions/current`: [L153–174](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/main.rs#L153-L174).
- Header всегда вызывает `self.absolute(path)`; при `cwd=None` тот просто возвращает относительный path, не используя известный host.workspace: [document L44–51](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/document.rs#L44-L51).
- Native documents создаются лениво независимо от panel: [ensure_document L62–91](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/tabs/mod.rs#L62-L91), [visible document rendering L247–253](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/tabs/view.rs#L247-L253).
- Panel также создаётся только при первом собственном использовании; sidebar может быть закрыт: [panels L64–101](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/panels/mod.rs#L64-L101).

Таким образом сохранённый document tab с закрытой Files sidebar не обязан предварительно прогреть panel. Clipboard ОС не проверялся; проверен корректный для host исходящий `clipboard` message, содержащий неправильный вид пути. Native GPUI startup не запускался.

### Направление исправления

Выделить разрешение session cwd из tree/git refresh, делать его для документа независимо от panel. Учитывать, что Host.workspace может быть только предварительной папкой до получения session metadata: нельзя бесконтрольно заменить authoritative session cwd глобальной рабочей папкой. Добавить document-only и sibling-panel regression.

## Проверки

- Чистая сборка Files: passed (`build.log`).
- Штатные Files: **24 passed** (`files-baseline.log`).
- Штатные SDK: **51 passed**, doctests 0 (`sdk-baseline.log`).
- 3 wire scenarios: copy cold→sibling panel, active missing with two actual polls, active announced positive control. Все observation assertions проходят.
- 2 desired regression checks ожидаемо красные: initial absolute clipboard и active refresh without extra navigation.
- Полный Desktop build, native окно, системный clipboard, реальный Core и файловая ОС fixture не запускались.

## Повтор

В чистой копии Extensions указанного SHA:

```sh
CARGO_TARGET_DIR="$PWD/target" cargo build --locked --manifest-path /path/to/extensions/Cargo.toml -p extension-files
python3 repro_copy_path.py
python3 repro_active_refresh.py
python3 repro_copy_path.py --require-fixed      # expected red before fix
python3 repro_active_refresh.py --require-fixed # expected red before fix
```

Можно передать `--binary /path/to/files`. Build target и бинарники не включены в ZIP. `source-provenance.json` фиксирует hashes source и свежесобранного бинарника. Исправления production-кода, commits, PR и публикация не выполнялись.
