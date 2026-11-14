# Дополнительный аудит установки, упаковки и build/update flow

Дата: 2026-11-13. Исследование только локальных фикстур, без production-изменений, публикаций, PR, live API или новых загрузок toolchain.

## Подтверждённые новые проблемы

### 1. P2: SDK release gate может успешно проверить старые executable вместо только что собранных

**Файл:** Desktop `scripts/release.py:90–103`, особенно 94–103.
**Причина:** оба `cargo build` сохраняют inherited Cargo configuration, но пути для smoke жёстко вычисляются как `<CARGO_TARGET_DIR>/debug/<binary>`. При `CARGO_BUILD_TARGET=x86_64-unknown-linux-gnu` Cargo складывает свежие native executables в `<CARGO_TARGET_DIR>/<host>/debug/`. Это обычная native-сборка, не попытка исполнить cross-target.

**Воспроизведено реальным Cargo 1.95.0, без network/dependencies и без mock subprocess:**
1. Два tiny Cargo package с ожидаемыми gate именами собираются production `release.sdk_gate`. Их binaries выводят `OLD`.
2. В обоих исходниках output меняется на `NEW`, а в environment добавляется `CARGO_BUILD_TARGET` с native host.
3. Повторно вызывается та же неизменённая `release.sdk_gate`. Оба новых executable реально собраны; прямой запуск каждого из `target/<host>/debug` печатает `NEW`.
4. Gate передаёт fixture smoke оба старых пути `target/debug`, smoke видит `OLD` + `OLD`, вся команда успешна.

Пустой cache вместо тихой ложной проверки даёт failure из-за отсутствующего executable. Повторный warm build опаснее: получается зелёный gate не для текущих исходников. В checked-in GitHub workflow переменная target не задана, поэтому это не заявление, что текущий pristine CI уже проверяет stale outputs.

**Исправление:** выбирать оба executable по emitted `compiler-artifact.executable` в успешном Cargo JSON stream, как это уже сделано в `scripts/cargo_binary.py`, а не угадывать target layout. Для независимого starter учесть его `--manifest-path`.

**Регрессионный тест:** warm un-targeted build, изменение sources, targeted native build; smoke обязан увидеть текущие outputs. Контроль без старых outputs тоже должен пройти.

Артефакты: `probe_sdk_gate.py`, `sdk-gate.log`, `sdk-gate-result.json`, `sdk-gate-fixture/`.
**Граница доказательства:** production Python gate + реальные Cargo/rustc/subprocesses; fixture smoke лишь исполняет переданные пути и фиксирует результат, не реализует настоящий module wire protocol. Полный Core/GUI не собирался.

### 2. P2/P3: смена pinned Ghostty dependency не обновляет существующий локальный cache и ломает повторную сборку

**Файл:** Desktop `scripts/terminal_toolchain.py:47–60,64–73,139–164`.
**Причина:** specification/receipt включает URL и expected hash, но архивы имеют ключ только `<name>.tar.gz`/`<name>-flat.tar.gz`. После смены pin receipt корректно становится невалидным, затем `download()` возвращает старый существующий архив, а `flatten_archive()` возвращает старый flat. `zig fetch` получает старый package, expected hash уже новый, setup завершается ошибкой. Новая загрузка по новому URL не происходит.

**Локальная fixture A→B:**
- Подготовка одной dependency `fixture` A успешна.
- Меняются URL и expected hash на B при том же имени.
- Повторная production `prepare()` падает `expected Zig hash ...B..., got ...A...`, сохранённый архив побайтно остаётся A.
- Тот же B с пустым `build/tools` проходит.

Это дефект upgrade/checkout-between-pins в warm developer checkout, не несовместимость текущих pinned sources и не bypass верификации: неверные bytes правильно отвергаются, но updater не умеет получить новые. Практический workaround: удалить именно устаревший архив и flat, а не весь Cargo/Zig cache.

**Исправление:** включить pin/content identity в имя source/flat cache или хранить matching source identity рядом и атомарно заменять пару при смене specification. Не очищать весь общий cache.
**Регрессионный тест:** одинаковое package name, A→B, тёплый root должен успешно подготовить B; A может остаться в отдельном keyed cache.

Артефакты: `probe_toolchain_cache.py`, `toolchain-cache-result.json`, `toolchain-cache-fixture/`.
**Граница доказательства:** production prepare/download/flatten/receipt, настоящие локальные tar archives и subprocess; Zig заменён минимальным fixture executable, который выдаёт hash содержимого вместо настоящего Zig package hash. Реальная сеть/Zig compilation не выполнялась.

## Выполненные проверки

- Desktop `python3 -m unittest discover -s scripts -p 'test_release*.py'`: **122 passed**, 4.931 s.
- Modules `python3 -m unittest discover -s tests -p 'test_package.py'`: **13 passed**, 0.050 s.
- Оба новых воспроизведения успешно подтвердили заявленные наблюдения.
- Desktop dedicated checkout `git status --short`: пусто; `git diff --check`: чисто.
- Отдельно просмотрены runtime path selection, full/partial source manifests, packaging rollback, source export, notices, independent package builders, vendored test projection и release publish workflow.

## Не выданы за новые находки

- Уже известный skip protocol/features validation для совместного `desktop extensions` partial build.
- Уже известная catalog revision/content рассинхронизация.
- `--agent=codex`/`--origin=...` не поддерживаются самим Rust parser, поэтому соответствующая ветка Python wrapper не является самостоятельной регрессией.
- Необновление общего `release-sources.json` при single-module install остаётся наблюдением для дополнительной проверки контракта. Доказательства реального неправильного release publication в этом проходе нет, отдельной подтверждённой находкой не считается.

## Точный охват и ограничения

Файлы, ranges, content SHA256 и число прочитанных строк перечислены в `coverage.tsv`. Полное чтение только перечисленных файлов; это не аудит всех 4 репозиториев и не заявление «каждая строка проекта проверена». В `src/launch.rs` прочитан только диапазон 1–210 для сверки CLI contract. Перечисленные ранее-known части переосмотрены, но не засчитаны как новые дефекты.

Не выполнялись: полный Cargo workspace gate, реальная GUI/window/compositor практика, release artifact compilation, сетевые загрузки Zig/deps, installer на настоящем пользовательском runtime, live provider/model runs, GitHub Actions или remote публикация. GitHub source SHA проверены read-only, результаты в `source-state.txt`.
