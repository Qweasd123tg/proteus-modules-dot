# Proteus Desktop: второй построчный проход, 2026-11-12

## База и границы

- Репозиторий: Proteus-harness/Proteus-desktop, HEAD и remote main: `75bf201764278eac4b50d156650edcf1429101ff`.
- Область: catalog install/update/download/build/cache, portable packaging, terminal lifecycle/input/display, image cache/budgets.
- `coverage.tsv` фиксирует **41 полностью прочитанный файл, 8634 строк**, плюс отдельно частичные диапазоны. Это охват данного прохода, не утверждение, что прочитан весь Desktop или каждый транзитивный dependency.
- Продакшен-файлы не изменены, коммитов/PR/push нет. Добавлены только отдельные стенды и журналы в `audit-round2/`.
- Предыдущие находки про корреляцию feedback и paged chat cache не повторяются.

## D2-01. Refresh публикует индекс нового каталога со старой revision при ошибке записи state [P2]

**Место:** `src/catalog/git.rs:228-233`; чтение смешанного состояния `141-145`; admission в `with_files`, `255-280`.

`refresh` сначала заменяет каталог checkout, затем отдельно записывает `.state-<key>.json`. При отказе последней записи опубликованный checkout не откатывается. `cached` читает state и индекс независимо. Получается метаинформация B с revision A; проверка stale catalog в `with_files` это пропускает и извлекает содержимое A.

**Воспроизведение на настоящих Git-файлах:**

1. Создать синтетический local repo A с entry version=A и `demo/SKILL.md = '# A contents'`.
2. `refresh` A, затем commit B (version=B, другие байты skill).
3. Сделать только собственный fixture state-файл read-only, вызвать `refresh` B. Получить `Permission denied`.
4. Вернуть запись state, вызвать `cached`: объявленная версия B, revision A.
5. `with_files` с revision из этого каталога успешно читает `# A contents`.

Стенд дважды дал одинаковый результат (`catalog-probe.log`, `catalog-probe-repeat.log`). В нём используются неизменённые production `packages`, `schema`, `skills`; `git.rs` и `source_export.rs` скопированы без изменений для Rust module-resolution. Полные SHA256 копий совпадают. `Source`/key/name взяты из production, UI не подменяет проверяемые операции. Ошибка записи инжектирована chmod только тестового файла, не трогает настройки компьютера или пользовательские данные.

**Эффект:** после неуспешного обновления и повторного открытия каталога можно установить старые байты под метаданными/версией нового пакета, вместо отказа stale guard. На нормальном успешном refresh этот тест не показывает сбой. Disk-full/short-write могут иметь другой исход; непосредственно воспроизведён отказ доступа, не все ошибки ФС.

**Исправление:** публиковать checkout и state как одну ревизию, например держать state внутри staged generation и переключать каталог одним rename. Дополнительно синхронизировать `cached` с refresh; одна блокировка чтения не исправляет смешанное состояние после уже завершившегося error-path. Атомарная запись только JSON тоже недостаточна.

**Регрессионная проверка:** отказ публикации state обязан оставлять полностью A либо возвращать `cached` ошибку, никогда B metadata + A revision. Отдельно проверить конкурентное чтение во время refresh.

## D2-02. Совместная portable-сборка Desktop+Extensions обходит protocol/features gate [P2]

**Место:** `scripts/portable.py:163-188`; `scripts/portable_state.py:15-46,85-105`.

`verify_protocol` действует только если выбран Desktop без Extensions. `verify_extension_source` вызывается только если выбраны Extensions без Desktop. Если выбраны оба компонента, а также при full rebuild, обе проверки обходятся; заключительный `read_record(stage)` проверяет наличие assets/executables, но не сопоставляет extension protocol/required_features с Desktop.

**Два раздельных воспроизведения:**

- Desktop protocol=4, extension protocol=5, requirements=[];
- Desktop protocol=4, extension protocol=4, required_features=['future.v99'], desktop_features=[].

Для каждого сценария extensions-only корректно отказывает. Та же source fixture при `--components desktop extensions` успешно публикует несовместимый пакет и заменяет прежний структурно-валидный protocol-4 destination. Лог `portable-protocol.log`, скрипт `portable_protocol_probe.py`.

**Ограничение стенда:** используется штатная `PortableSelectionTests`. Компиляция, source resolution, часть assets/notices/provenance и package producer заменены fixtures; настоящие `main`, `assemble`, protocol/feature validators, `read_record`, `publish` выполняются. Это доказательство ошибки packaging control flow, не реальная сборка бинарников и не прогон GUI. Никакого утверждения о несовместимости текущих pinned sources нет. Реалистичный путь к различающимся версиям: поддерживаемые source overrides или соседние checkouts в `scripts/sources.py`.

**Исправление:** перед publish для любого scope проверять фактически собранные extension manifests против desktop_protocol и desktop_features итогового stage. Не полагаться только на preflight выбранной стороны.

**Регрессионная проверка:** оба сценария выше, включая `--full`, должны завершаться до замены destination, старый пакет остаётся нетронутым.

## Прогоны

- Python release baseline: **122/122**, `release-tests-with-toolchain.log`.
- Catalog/schema/source-export, actual production source in isolated Rust crate: **8/8**, `catalog-unit-tests-complete.log`.
- Terminal, actual production crate sources, headless Alacritty path: **14/14**, `terminal-tests.log`, включая настоящий shell-output smoke, parser reset, Unicode/ANSI, bounded queues, input/password, resize/scroll/title/bell.
- Image budget/cache, actual production source in isolated Rust crate: **6/6**, `resource-tests.log`.
- Новые probes **подтверждают существующее ошибочное поведение**, их exit 0 не означает, что ошибки уже исправлены.
- Первый Python запуск без toolchain PATH дал 8 environment errors (`cargo not found`); повтор с активированным toolchain полностью прошёл. Первый isolated catalog `cargo test` не видел вложенный test-module; после добавления неизменённой копии test-module 8/8. Это проблемы первоначальной настройки стенда, не defects продукта.

## Воспроизводимые команды

Из корня этого checkout, с Rust 1.95 и cargo в PATH:

```sh
python3 audit-round2/portable_protocol_probe.py
cargo run --manifest-path audit-round2/catalog-probe/Cargo.toml
cargo test --manifest-path audit-round2/catalog-probe/Cargo.toml
python3 -m unittest discover -s scripts -p 'test_release*.py'
PROTEUS_TERMINAL_ENGINE=alacritty cargo test --manifest-path audit-round2/terminal-probe/Cargo.toml --lib
cargo test --manifest-path audit-round2/resource-probe/Cargo.toml --lib
```

Catalog chmod probe требует Unix и запуска не от root. Каждый повтор оставляет новую собственную fixture-папку для осмотра. Полный GUI, renderer/atlas, Wayland, реальная совместная portable release и Ghostty/Zig здесь не запускались. По прочитанным terminal/resource путям новых подтверждённых дефектов в этом проходе нет, что не равно доказательству их отсутствия.
