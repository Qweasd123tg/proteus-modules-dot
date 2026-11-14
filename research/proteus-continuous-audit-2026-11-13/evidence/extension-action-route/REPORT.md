# Proteus: действие из старого дерева панели исполняется в новой сессии

## Результат

**P2, подтверждённый протокольный сбой на настоящем Files+SDK; нативный GUI-маршрут установлен по исходникам, но не выполнен кликами.**

При переходе из чата A в чат B существующая панель Files сохраняет показанное дерево A до ответа расширения. Контекст процесса к этому времени уже B. Клик по ещё видимой строке A не содержит identity/generation той сессии, из которой была построена строка. SDK обрабатывает его в текущем B. Если относительный путь существует в обоих проектах, открывается содержимое B вместо показанного A. Если путь есть только в A, открытие получает ошибку файла в B.

Это не missing initial subscription, не `Runtime.error` при off/on, не SDK poll starvation и не ранее найденный fallback после ошибки rehost. Здесь обычная смена выбранного чата, без rehost и без render error.

## Ревизии и метод

2026-11-13, remote HEAD повторно сверены через `git ls-remote origin HEAD`:

- Desktop `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.

Для сборки взят чистый `git archive HEAD` Extensions, отдельный Cargo target, без патчей. Использован настоящий бинарник Files с настоящим SDK. Вместо Core работает HTTP fixture на loopback. Все пути, токены и содержимое синтетические. Fixture обслуживает только GET; POST запрещён. Production-исходники, refs и пользовательские файлы не изменялись; ничего не публиковалось.

## Причинная цепочка в Desktop

1. Панель сохраняется в `Workspace.panels` между чатами; [ensure_panel](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/panels/mod.rs#L64-L82) возвращает прежний view, а её Host динамически следует root текущей области.
2. [scope_event](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L260-L305) на SessionOpened объявляет новый Context, передаёт Event, сбрасывает только ContentQueue и запрашивает Render. Оно не очищает дерево DeclarativeView и не приостанавливает его действия.
3. [DeclarativeView::render](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/view.rs#L427-L469) продолжает строить элементы из `self.root`. `waiting` включается только при отсутствии root. Отдельной проверки принадлежности root текущей сессии нет.
4. [act](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/view.rs#L330-L341) передаёт только sequence, view, action и value. [Action wire](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/declarative/protocol.rs#L114-L121) не содержит session/generation принятого дерева.
5. SDK [route_message](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/sdk/src/host/scopes.rs#L131-L139) адресует action через текущий view_context, уже переключённый Context(B). Затем вызывает `Extension::action`.
6. Files [file](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/main.rs#L278-L301) открывает переданный путь. [Desktop OpenDocument](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime.rs#L579-L608) тоже разрешает источник по **текущему** attached context, а не по сессии показанного пользователю дерева.

Монотонный action sequence защищает порядок ответов, но не эту принадлежность: после клика sequence становится 1, поэтому ожидавшийся B render с sequence 0 может быть отброшен `show`, однако само действие уже направлено в B.

## Воспроизведение настоящим процессом

`repro_stale_action.py` создаёт контекст A и открывает Files panel. В начальном дереве есть `only-a.txt` и `shared.txt`. Затем передаются те же Context(B), Event(session_opened B), Render(B), которые выдаёт Desktop для переключения. HTTP-ответ `/sessions/current` для B удерживается барьером; процесс не может прислать новое дерево B. В этот момент отправляется обычный Action из старого дерева. После отпускания барьера SDK обрабатывает очередь.

Проверены четыре сценария:

| Сценарий | Что выбрано | Реально адресованная сессия | Результат |
| --- | --- | --- | --- |
| Контроль до switch | only-a.txt в A | A | содержимое A |
| Stale click | only-a.txt, B tree ещё не пришло | **B** | ошибка отсутствующего файла B |
| Stale collision | shared.txt, B tree ещё не пришло | **B** | **содержимое B**, хотя выбрана ещё показанная строка A |
| Контроль после нового tree | only-b.txt в B | B | содержимое B |

В stale-сценариях барьер и пустая очередь вывода проверяют, что новый tree не мог уже прибыть до действия. JSON сохраняет полный вход/выход процесса и список реальных HTTP GET. Прогон `--require-safe` ожидаемо падает с exit 1 на инварианте «действие из дерева A не должно читать файл через B».

### Существенная граница доказательства

Тест **не** запускает GPUI, Core, Desktop event loop или window manager. Он не делает настоящий mouse click и не измеряет частоту/длительность окна в GUI. Задержка fixture детерминированно воспроизводит предусмотренную synchronous HTTP паузу расширения; Desktop-side сохранение дерева и отсутствие route guard доказаны чтением production source, не end-to-end скриншотом.

Ответ `open_document` разрешается тестом в текущем B и посылается обратно как document render. Это моделирование маршрута хоста, соответствующее приведённому коду Desktop; сам последующий `/workspace/file` выполняет реальный Files. Не следует называть его полной интеграционной проверкой Desktop.

Никакие rename/delete/stage/commit операции не выполнялись. Те же незафиксированные действия используются другими контролами, поэтому потенциально затронуты и записи, но последствия записи в неправильный проект здесь **не проверены** и не заявляются как наблюдённый результат.

## Проверки

- Clean Files build: PASS.
- `cargo test --locked -p extension-files -p proteus-extension`: **24 Files + 51 SDK passed**, doc tests 0.
- Wire regressions: **2 observed failures + 2 positive controls passed** (обычный observed mode проверяет наличие дефекта).
- Desired-safe invariant: expected FAIL, exit 1.
- Full Desktop suite, native GUI, real Core, packaging: не запускались.

## Направление исправления

Хранить адрес/поколение, к которому относится **принятое дерево**, отдельно от текущего scope. Сразу при смене session/context не допускать действий из старого дерева до принятия ответа для нового поколения. Для надёжного контракта передавать это поколение в Render/View/Action и отвергать несовпавшие действия; одного sequence или проверки живого view недостаточно. Нужно покрыть A→B→A, pending menu/input callbacks, in-flight HTTP и retained/rehost views. Кандидат-патч здесь не добавлен: согласованное изменение host+SDK требует отдельной focused native проверки.

## Повтор

```sh
# Чистый Extensions checkout указанного HEAD; отдельный CARGO_TARGET_DIR.
cargo build --locked -p extension-files
cargo test --locked -p extension-files -p proteus-extension
python3 repro_stale_action.py --binary /path/to/target/debug/files
python3 repro_stale_action.py --binary /path/to/target/debug/files --require-safe
```

В `source-provenance.json` закреплены HEAD и SHA-256 всех рассмотренных исходников. Сборочные артефакты и checkout не включены в переносимый архив.
