# Proteus Files: обновление дерева после Expand All и временной ошибки

Дата: 2026-11-13. Два новых подтверждённых дефекта, оба P2. Потери данных нет: дерево не показывает существующие файлы и требует лишнего действия пользователя.

## Версии и границы проверки

- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
- Core `89997df995df7c39b713e16aba216ecb19c8f497`.
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`.
- Все три локальных HEAD совпали с `git ls-remote origin HEAD` при этой проверке.
- Extensions извлечён через `git archive HEAD` в отдельную папку. Собран свежий `files` с собственным Cargo target. Не использовался бинарник другого аудита.
- Проверен реальный неизменённый Files + SDK через NDJSON и настоящий пятисекундный polling. Подменена только Core HTTP API: синтетические данные на loopback, без пользовательских файлов.
- Для быстрых red/green регрессий добавлены только тесты `tree_tests.rs` в изолированную копию. Основной бинарник собран до этих test-only добавлений. Исходный checkout и production-код этим аудитом не менялись; никаких commit/push/PR.
- Нативное окно Desktop и живой Core не запускались. Не утверждается, что воспроизведён конкретный серверный источник HTTP 503. Временный отказ API введён намеренно; для Files все ошибки загрузки превращаются в один `None`.
- Это не повторение split-document visibility, отсутствующего startup navigation, document-only Copy path, rename/retarget, или предела fold-chain 33. Первый новый сценарий использует только два уровня папок и одну панель.

## 1. Expand All не включает предков свёрнутой строки в обновление

**Сценарий:** есть `src/lib/existing.rs`. Files сворачивает папки в одну строку `src/lib`. Пользователь выбирает её штатное меню «Развернуть всё». После этого снаружи появляется `src/new.rs`.

**Наблюдение на реальном бинарнике:**

- `existing.rs` виден, строка `src/lib` раскрыта.
- После двух реальных poll (~10 секунд) `src/new.rs` отсутствует.
- `/workspace/list?path=src/lib` вызван 3 раза, но `/workspace/list?path=src` только 1 раз (начальное чтение). Это не задержка до очередного poll: предок исключён из всех обычных повторных загрузок.
- Положительный контроль с обычным раскрытием той же строки: оба endpoint вызваны 3 раза, новый файл виден уже на первом poll.
- `run_settled` снимает старую свёртку, но теперь `src` оказывается закрытым. После ручного раскрытия появляется новый файл. Старое состояние раскрытия потеряно по той же причине.

**Причина:** видимая folded-строка адресуется самым глубоким путём. Обычный `expand` идёт через `heads` и раскрывает всю цепочку. `expand_all` стартует сразу с полученного глубокого пути; предок `src` остаётся только в кэше lookahead, не в `expanded`. Периодический `invalidate(false)` сбрасывает только `expanded`, поэтому устаревшее содержимое `src` сохраняется.

Исходники на точном SHA:

- [Меню передаёт путь строки](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/menu.rs#L99-L104).
- [Вызов expand_all](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/operations.rs#L42-L48).
- [Обычный expand обрабатывает всю свёрнутую цепочку](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/tree.rs#L241-L264).
- [expand_all не учитывает heads](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/tree.rs#L291-L314).
- [Периодическое обновление только expanded](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/tree.rs#L118-L129).

**Направление исправления:** единый инвариант раскрытия folded-строки для `expand` и `expand_all`: все её составные папки считаются раскрытыми и обновляемыми. Сохранить существующие ограничения глубины/числа запросов. Не заменять это постоянной перезагрузкой всех закрытых папок.

Доказательства: `folded-expand-all.json`, `folded-expand.json`, `folded-wire-red.log`.

## 2. Один временный отказ чтения дочерней папки сохраняется после восстановления API

**Сценарий:** пользователь раскрыл `src`, видит `src/visible.rs`. Следующий периодический запрос списка `src` один раз получает HTTP 503. Все последующие ответы API снова успешны.

**Наблюдение на реальном бинарнике:**

- На первом ошибочном poll содержимое `src` пропадает, но строка ещё отмечена раскрытой.
- На следующем poll папка уже закрыта. Ошибка не показана пользователю.
- За три poll (~15 секунд) запросов списка `src` всего 2: начальное успешное чтение и единственный отказ. После восстановления API повторного запроса нет.
- Ручное раскрытие сразу восстанавливает содержимое.
- Положительный контроль с однократной ошибкой корневого списка: SDK показывает ошибку поверх старого дерева; следующий poll перечитывает корень, и содержимое восстанавливается без действий пользователя.

**Причина:** `listing()` через `.ok()` кэширует любой отказ как `None`. `visit()` на `None` удаляет папку из `expanded`, хотя это не доказательство удаления папки. Следующие partial refresh сохраняют этот `None`, так как папка больше не раскрыта. `expand()` умеет сбрасывать такой negative cache, но только после ручного действия.

Исходники:

- [Кэширование ошибки без различения причины](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/tree.rs#L131-L136).
- [Удаление expanded после ошибки](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/tree.rs#L179-L190).
- [Ручное восстановление сбрасывает None](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/tree.rs#L254-L263).

**Направление исправления:** не приравнивать временный отказ к исчезнувшей папке. Сохранять пользовательское раскрытие и возможность повторного чтения на следующем poll; удалять состояние по авторитетному списку родителя (для этого уже есть `prune`). Полезно сохранить последний успешный список и отобразить ошибку, а не молча убирать содержимое.

Доказательства: `transient-child-repro.json`, `transient-root-control.json`, `transient-wire-red.log`.

## Проверки и воспроизведение

Результаты:

- `cargo build --offline --locked -p extension-files`: PASS, production HEAD.
- `cargo test --offline --locked -p extension-files -- --skip trace_`: 24 исходных теста PASS.
- `cargo test --offline --locked -p proteus-extension`: 51 тест PASS.
- `cargo test --offline --locked -p extension-files trace_`: 2 ожидаемых FAIL и 2 контрольных PASS, только тестовые добавления в `regression-tests.patch`.
- `python3 repro_document_controls.py`: PASS, пять настоящих poll; смена kind и восстановление после ошибки чтения активного документа.
- `python3 repro_tree_refresh.py`: PASS как проверка наблюдаемого дефектного поведения, четыре сценария.
- `python3 repro_tree_refresh.py --case folded --require-fixed`: ожидаемый FAIL.
- `python3 repro_tree_refresh.py --case transient --require-fixed`: ожидаемый FAIL.

Для повторения на чистом checkout того же SHA:

```sh
cargo build --locked -p extension-files
python3 /path/to/evidence/repro_tree_refresh.py --binary /path/to/checkout/target/debug/files
python3 /path/to/evidence/repro_tree_refresh.py --binary /path/to/checkout/target/debug/files --case folded --require-fixed
python3 /path/to/evidence/repro_tree_refresh.py --binary /path/to/checkout/target/debug/files --case transient --require-fixed
patch -p1 < /path/to/evidence/regression-tests.patch
cargo test --locked -p extension-files trace_
```

Обычный wire-прогон занимает около 50 секунд. `--require-fixed` должен стать зелёным после исправления. HTTP-сервер создаётся только на `127.0.0.1`; все пути и содержимое синтетические.

Дополнительные положительные контроли `repro_document_controls.py`: в активном документе `text → binary → too_large → text` и однократная ошибка чтения с последующим восстановлением. Этот путь проверяется отдельно, чтобы не переносить вывод о застрявшем кэше дерева на кэш документов.

`source-provenance.json` содержит SHA-256 бинарника и сверку 31 исходного файла с HEAD. `verified-heads.txt`, логи и полные wire/API трассы позволяют отличить источник, сборку, введённый отказ и реальный результат. Исправлений production и публикации нет.
