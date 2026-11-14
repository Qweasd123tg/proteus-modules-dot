# Proteus Desktop Extensions: продолжение построчного аудита

Репозиторий: https://github.com/Proteus-harness/Proteus-desktop-extensions
Зафиксированный main: `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
Повторный `git ls-remote` у GitHub origin исходной копии вернул тот же SHA.
Работа выполнена в отдельной копии `extensions-line-audit`. Production-код не изменён: только 54 строки regression tests в двух файлах. Публикаций, коммитов и PR нет.

## Новые подтверждённые дефекты

### EXT-L1: потеря footnote при разделении Markdown на native code/prose (P2)

- Место: `packages/markdown-render/src/references.rs:11-35`, `render.rs:205-215` и разделение root code/prose в `render.rs:100-156`.
- `references::collect` сохраняет document scope обычных ссылок через `Node::Definition`, но не `Node::FootnoteDefinition`. Каждый фрагмент prose компилируется отдельно.
- Вход: `Read this note[^n].\n\n` + fenced rust block + `\n\n[^n]: Important footnote text.\n`.
- Результат: ссылка показывается буквально `[^n]`, `Important footnote text.` отсутствует во всём render tree. Это потеря отображаемого содержимого, не удаление исходного файла.
- Контроль без разделяющего code fence: footnote body и `data-footnote-ref` присутствуют.
- Подтверждено и unit test на production Document, и настоящим `markdown-render` процессом через protocol 4 NDJSON.
- Исправление должно сохранять document-scoped footnote definitions, порядок/нумерацию и обратные ссылки; наивное дублирование definitions по сегментам может создать отдельные наборы footnotes.
- Permalink: https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/markdown-render/src/references.rs#L11-L35

### EXT-L2: тёплый Markdown cache после изменения строки закрывающего fence показывает другой документ (P2)

- Место: `packages/markdown-render/src/render.rs:50-58,128-142`.
- Закрытый fence считается immutable, если `source[end]` был newline. Но cache fingerprint сохраняет только `source[..end]`, не включая этот newline и не проверяя его при reuse.
- Сначала render ` ```mermaid\nA-->B\n```\n `; затем в том же view заменяем исходник на ` ```mermaid\nA-->B\n``` no longer a closing fence\n ` (пробелы с краёв здесь только для оформления).
- Warm output: native Mermaid `A-->B` + prose `no longer a closing fence`.
- Cold output при том же окончательном исходнике: незакрытый native code block с текстом `A-->B\n``` no longer a closing fence`.
- Подтверждено unit test и реальным NDJSON-процессом с warm/cold view; source revisions корректно увеличивались.
- Ограничение: это изменение/замена исходника, не чистый append-stream. Не выдавать за ошибку любого streaming append.
- Возможное исправление: учитывать terminator закрывающей строки в cache validity, включая корректную обработку CRLF/EOF, или перепроверять пограничную строку перед reuse.
- Permalink: https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/markdown-render/src/render.rs#L50-L58

### EXT-L3: files не раскрывает свёрнутую цепочку из 33 папок (P3)

- Место: `packages/files/src/tree.rs:219-264`, `CHAIN = 32`.
- `fold()` начинает с первой папки и делает 32 перехода, возвращая 33-ю. `expand()` начинает с той же первой папки, но делает 32 вставки в expanded, т.е. до 32-й. Условие open в строке проверяет 33-ю.
- Repro: `d/d/.../d/leaf.txt`, 33 директории; три последовательных expand возвращают единственную закрытую строку, leaf не появляется.
- Контроль: 31 и 32 директории раскрываются и показывают leaf.
- Подтверждение: test вызывает настоящие `Project::lines/expand` и production Listing/Entry с in-memory loader. Полный Desktop GUI не запускался.
- Исправление: согласовать число папок, а не число переходов, и гарантировать включение конечного path, который реально показан строкой.
- Permalink: https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/tree.rs#L219-L264

## Доказательства

- `regression-tests.patch`: только три теста; применять на указанном SHA. Все три ожидаемо падают до исправления.
- `markdown-regressions.log`, `files-regression.log`: вывод с actual render tree / collapsed rows.
- `wire_repro.py`: отдельный воспроизводитель, использует настоящий binary, без Core и сетевых запросов.
- `wire-input.ndjson`, `wire-output.ndjson`, `wire-stderr.txt`: полные синтетические сообщения protocol 4 и ответы.
- Запуск regression: `cargo test --locked -p extension-markdown-render line_audit_tests -- --nocapture`; `cargo test --locked -p extension-files line_audit_deep_folded_row_can_open_its_leaf -- --nocapture`.
- `workspace-filtered-tests.log`: 218 штатных Rust tests проходят; исключены три добавленных failing regression tests и один штатный Mermaid lifecycle test.
- Исключённый штатный `different_sessions_share_one_worker_and_last_close_and_eof_reap_it` не работает в данной среде: `/proc/<pid>/task/<tid>/children` отсутствует даже у минимального Python→sleep subprocess. Два независимых прогона дали worker children=0 после успешного SVG. Это ограничение наблюдения за процессами в среде, не подтверждённый дефект продукта. Первичный лог сохранён отдельно.
- `node-tests.log`: 11/11 Mermaid Node tests проходят, включая несколько wire requests и exit после EOF.
- `python-tests-ready.log`: 58/58 Python package/catalog/schema/bundle tests проходят, включая запуск всех собранных standalone packages вне checkout. Команда: `PYTHONPATH=tests python -m unittest tests.test_bundle tests.test_catalog tests.test_package_selection tests.test_schema` с доступными Cargo и CARGO_TARGET_DIR. Первые попытки без test import path / Cargo PATH сохранены, но не являются дефектом продукта.

## Реальный охват

`coverage.tsv` и `coverage.json` содержат original SHA-256 каждого файла и точно учтённый диапазон. Консервативно прочитано 9 206 строк из 18 744 строк Rust исходников и тестов в sdk/src и packages, 48 из 80 файлов затронуты чтением. Счёт включает comments/blanks; не является test coverage. Дополнительно прочитаны package.py, Mermaid worker.mjs, svg-theme.mjs, update-vendor.py; docs просмотрены отдельно. Vendored Pele и experiments целиком не аудированы. Частично прочитанные тестовые диапазоны сверх ledger не засчитывались.

Основной акцент: SDK host/context/session/inbox/documents, Files operations/tree/path safety, Git main/cache/document, Markdown и JSON boundary/render, Mermaid worker lifecycle/cache/theme, Plan preferences, usage/quota/context/analysis. Не заявлять, что прочитана каждая строка всего репозитория.

Три ранее найденных SDK проблемы (late settings ACK, core:false poll и cross-session render-error tree) не включены в новые находки и повторно не публиковались.
