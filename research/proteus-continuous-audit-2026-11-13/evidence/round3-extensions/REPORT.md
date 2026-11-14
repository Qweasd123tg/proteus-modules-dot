# Extensions: продолжение построчного аудита, раунд 3

## Снимок и границы

- Репозиторий: `Proteus-harness/Proteus-desktop-extensions`.
- Проверенный commit: `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
- Remote `main` сверён перед работой и повторно после проверки: тот же SHA.
- Работа велась в отдельной чистой копии. Изменён только тестовый файл `packages/git/src/tests.rs`; исходники production, GitHub, настройки и реальные пользовательские сессии не изменялись.
- Данные тестов синтетические, HTTP только loopback. Native GUI и реальный Core в этом раунде не запускались.

## Новая подтверждённая проблема

### P3: имя файла с `dir:` конфликтует с внутренними ID папок Git inspector

Код: [details.rs:30–53](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/details.rs#L30-L53), [details.rs:185–205](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/details.rs#L185-L205).

Условия: в коммите есть допустимый для Unix/Git файл `dir:notes.txt`.

1. `files_in` выдаёт для файла raw path как `id`, а для папок использует `dir:<path>`.
2. `detail_file` любое `id` с `dir:` считает папкой. Выбор реального файла не устанавливает `commit_files`, не открывает его diff, а переключает состояние несуществующей папки `notes.txt`.
3. Если одновременно изменён `notes.txt/inside.txt`, файл `dir:notes.txt` и папка `notes.txt` получают одинаковый ID `dir:notes.txt`.

Два регрессионных теста используют штатную генерацию дерева и штатный обработчик action. На неизменённых production-исходниках оба падают:

- `audit_commit_file_with_dir_prefix_is_opened_as_a_file`: фактически `None`, ожидался выбранный файл `Some("dir:notes.txt")`.
- `audit_commit_inspector_file_and_folder_ids_are_distinct`: 3 строки, но только 2 уникальных ID; фактические ID `["dir:notes.txt", "dir:notes.txt", "notes.txt/inside.txt"]`.

Масштаб: локальный дефект навигации в inspector, не потеря файлов и не уязвимость. Для обычных имён файлов проблема не заявляется. Native GUI визуально не проверялся; нарушение контракта ID и выбор неверной ветки обработчика воспроизведены непосредственно.

Направление исправления: дать файлам отдельное пространство ID (например `file:<path>`), снимать только известный префикс при обработке и сохранять исходный path для выбора diff. Добавленные тесты получают ID из production-дерева, поэтому проверяют и генератор, и обратное преобразование, а не привязаны к нынешнему raw ID.

Артефакты: `git-regression-tests.patch`, `git-regressions.log`. Production-патч не применялся.

## Прогоны

Общий результат штатных тестов этого раунда: **208 passed, 0 failed**. Отдельно **2 новых регрессионных теста ожидаемо failed** по одной новой проблеме. Старые 6 находок в этот результат не включены и повторно не заявляются.

1. `cargo test --locked -p extension-git -p extension-files -p extension-model -p extension-mode -p extension-analysis -p extension-context -p extension-usage -p extension-plan -p extension-json-render -p extension-markdown-render -- --skip audit_commit_`
   - 153 passed; исключены ровно 2 новых регрессионных теста.
   - Лог `component-baseline.log`.
2. `cargo test --locked -p proteus-extension -p extension-quota -p extension-terminal`
   - 55 passed, 0 failed.
   - Лог `sdk-quota-baseline.log`.
3. `cargo test --locked -p extension-git audit_commit_ -- --nocapture`
   - 2 failed, 35 штатных Git-тестов отфильтрованы.
   - Лог `git-regressions.log`.

Использован существующий Rust toolchain/target cache. Mermaid Node worker, Latex renderer и полные Python/Node suites в этом раунде заново не гонялись; результаты прошлых прогонов не выдаются за новые.

## Учёт прочтения

Проверены SHA-256 всех унаследованных записей предыдущего coverage относительно указанного Git HEAD.

- Ранее: 9 206 / 18 744 строк Rust.
- В этом раунде закрыты оставшиеся **9 538** строк.
- Суммарно: **80 / 80 собственных Rust source/test файлов, 18 744 / 18 744 строк** согласно прежнему inventory.
- Основные новые блоки: Git model/history/graph/panel/details/documents; Files documents/menu/icons; Analysis details/nodes/summary/text; Model/Mode/Terminal; Context/Usage views; Plan model; непрочитанные тесты и оставшиеся renderer/SDK test ranges.

Это именно учёт построчного прочтения двух раундов, включая комментарии, пустые строки и тесты, а не branch/test coverage и не гарантия отсутствия дефектов. Все production-файлы из этого inventory теперь прочитаны; никаких утверждений о полном аудите vendored-кода, экспериментов, всех документов, манифестов либо всего репозитория здесь нет. `coverage.tsv` и `coverage.json` сохраняют старый диапазон, диапазон этого раунда, совокупный диапазон и hash каждого файла.
