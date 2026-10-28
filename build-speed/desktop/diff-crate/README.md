# Desktop: отдельная тестовая граница для diff-парсера

> В новой tabs-ветке runner вынесен в `../pure_crate.py`, а `qualify_diff.py` — фиксированный wrapper. Ни branch/head [исходного PR41](https://github.com/Qweasd123tg/proteus-modules-dot/pull/41), ни его результат не изменены. Ниже сохранено описание diff-only границы; новый composed tabs gate и ограничения — в [tabs README](../tabs-crate/README.md). Schema 2 сохраняет прежние source/files/registry/8 test identities; новый shared runner не наследует прежний hosted PASS автоматически.

Статус на момент подготовки: extraction прошёл независимый source review; 14 AST-extracted synthetic parser cases прошли в памяти; полный controller и все product-команды ещё NOT_RUN. Актуальный результат будущего hosted запуска определяется только его receipt для точного commit. Цель — проверять чистый парсер отдельно от GPUI, не подменять измерения shipping-клиента dev-сборкой.

## Что меняется

Из [src/diff](https://github.com/Proteus-harness/Proteus-desktop/tree/50f8b53b686816e7e32b89901aa6ed399826fb37/src/diff) в GPL-крейт `crates/diff` / `proteus-diff` перемещаются 3 файла: 583 строки, 20 434 UTF-8 байта, 8 существующих unit-тестов. `mod.rs` становится `src/lib.rs`; содержимое всех трёх файлов побайтно неизменно. Новые алгоритмы, тестовые подмены и фреймворки не добавляются.

В [root Cargo.toml](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/Cargo.toml) добавляются workspace member и path dependency. `default-members = [".", "crates/diff"]` сохраняет охват обычного `cargo test`: root-тесты и все 8 перемещённых тестов. Раньше non-virtual workspace без default-members по умолчанию выбирал root. `client-common` по-прежнему включён в полном workspace gate, а не добавлен в default scope.

В [src/main.rs](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/main.rs) `mod diff;` заменён root-import `use proteus_diff as diff;`. Это обычная Rust library dependency, не процесс, dynamic ABI или hot reload. Все шесть caller-файлов продолжают обращаться к `crate::diff` без правок.

`Cargo.lock` меняется вручную только на новый local package `proteus-diff` → `serde` и ребро `proteus-native` → `proteus-diff`. Версии, source, checksum и все остальные dependency entries неизменны. Cargo-проверка lockfile пока NOT_RUN.

## Установленная граница

| До | После |
| --- | --- |
| `src/diff` — модуль binary crate proteus-native; имя тестового фильтра не исключает компиляцию root/GPUI | Самостоятельная library test target proteus-diff |
| 8 parser-тестов в native test binary | Те же 8 тестов в diff library test binary |
| UI/model parsing/highlighting живут рядом в одном binary graph | Renderer/highlighting и widget validation остаются в native; только pure parsing отделён |
| Полный runner подготавливает extension binaries | Прямой targeted Cargo command не вызывает этот runner |

Новый manifest имеет ровно одну прямую зависимость: `serde = { version = "1", features = ["derive"] }`. По закреплённому lockfile её цепь содержит 7 registry packages: serde 1.0.229, serde_core 1.0.229, serde_derive 1.0.229, proc-macro2 1.0.107, quote 1.0.47, syn 3.0.7, unicode-ident 1.0.26. Это описание зависимостей из исходников, не результат `cargo tree` или замер. Rust standard library и test harness здесь не посчитаны.

В новом crate нет GPUI, Core, HTTP, process или filesystem API, build.rs либо dev-dependencies. Макрос serde остаётся обычной compile-time зависимостью, а не обещанием «никакой код сборки не запускается».

Проверены все 250 Rust-файлов `src/` и `tests/` на этом pin. Прямые внешние потребители:
- [declarative/widget.rs:174](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/declarative/widget.rs#L174): публичный `FileInfo`.
- [ui/diff/mod.rs:20,51,87](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/ui/diff/mod.rs#L20): модели и `parse`.
- [ui/diff/file.rs](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/ui/diff/file.rs#L6): `File`, `Kind`.
- [ui/diff/lines.rs](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/ui/diff/lines.rs#L6): `File`.
- [ui/diff/row.rs](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/ui/diff/row.rs#L2): `File`, `Kind`, `Line`, `Pair`.
- [ui/diff/syntax.rs](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/ui/diff/syntax.rs#L3): `File`, `Kind`; native highlighting test также вызывает `parse`.

Обратных ссылок из этих трёх pure-файлов на приложение нет; private `File::finish/note`, `pairs` и `parse::files` остаются внутри нового crate. Публичные структуры, поля, enum variants, derives, serde attributes и сигнатура parse не меняются. Rust type identity и symbol paths получают новую crate-границу; это не утверждение бинарной или ABI-эквивалентности.

## Команды после отдельно разрешённого применения кандидата

Из корня Desktop, с закреплённым Rust 1.95.0; Linux x86_64 также требует lld из [.cargo/config.toml](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/.cargo/config.toml).

Только 8 parser-тестов:
```sh
cargo test --locked -p proteus-diff --lib --jobs 2 -- --test-threads=4
```

При необходимости логические тесты в неизменённом release-профиле:
```sh
cargo test --release --locked -p proteus-diff --lib --jobs 2 -- --test-threads=4
```

Это команды для нового crate ПОСЛЕ применения; на исходном commit пакета ещё нет. Здесь они НЕ запускались. Cargo может по-прежнему разрешать общий workspace и читать или получать registry/git metadata; отсутствие GPUI в selected compile graph не гарантирует полностью offline first run. Для unit-команды не нужны подготовленные Core/extension binaries или UI, но toolchain и источники выбранных зависимостей нужны.

Полный поддерживаемый gate по-прежнему:
```sh
python3 scripts/test.py
```
Он сам добавляет `--workspace`, проверяет лицензии и заранее готовит реальные extension binaries. Не передавайте второй `--workspace`. Этот полный путь не стал «лёгким» и не запускался в рамках работы.

Обычный `cargo test` сохраняет перенесённые тесты за счёт default-members. Явный `cargo test -p proteus-native` проверяет только выбранный пакет и больше не включает эти 8 тестов — используйте пакет `proteus-diff` или workspace. Старый фильтр `diff::tests::...` меняется на `tests::...` в выбранном crate. В 36 невендорных Markdown/TOML/Python/YAML файлах на pin не найден документированный вызов такого старого фильтра; README/AGENTS направляют на scripts/test.py.

Два связанных теста сознательно остаются native:
- [closed diff widget / serde validation](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/declarative/widget/tests.rs#L118);
- [syntax/highlight UTF-8 ranges](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/src/ui/diff/syntax.rs#L133).

## Что пересобирается и что нельзя обещать

| Изменение | Targeted diff test | Shipping native release |
| --- | --- | --- |
| Только UI | Сам diff crate не изменён; Cargo может повторно запустить готовые тесты | Native crate и финальная линковка; зависимости по freshness |
| diff parser/model | Diff crate/test harness; неизменённые зависимости переиспользуются, если Cargo признаёт их fresh | Diff library, downstream native и финальная линковка |
| Только diff unit-тест | Test target diff; production code unchanged | Изменение файла с cfg(test) может всё равно сделать Cargo unit dirty; не обещаем отсутствие компиляции |
| serde version/features, toolchain, target, flags | Может инвалидировать соответствующие зависимости | Также зависимые native units |

Shipping performance сравнивают всё той же командой:
```sh
cargo build --release --locked -p proteus-native --jobs 2
```
Все существующие profile sections сохраняются побайтно: release opt-level 3, ThinLTO, codegen-units 1, strip true; dev и fast также не редактируются. Однако сама crate-граница меняет codegen и возможности оптимизации. Release byte-equivalence, runtime speed, RSS/PSS и время сборки **NOT_MEASURED**. ThinLTO всё ещё может обрабатывать cross-crate code; native relink не исчезает. Конкретно в fast перемещённый код теперь наследует CGU16 вместо native package override CGU256. Это следствие новой границы, а не правка профиля. Не отключаем LTO, не используем fast/dev как замену shipping-измерению.

Новый default build scope root + diff выбирает library, которая уже dependency root; не добавляет новый процесс или executable. Это не изменение режима portable packaging и не обещание мгновенной сборки.

## Лицензия и сохранность

[AGENTS.md](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/AGENTS.md#L69) требует GPL-3.0-or-later для приложения и symlink для каждого crate. Новый crate сохраняет GPL-3.0-or-later; код не переносится в Apache `client-common`. `crates/diff/LICENSE-GPL` — Git mode **120000**, точное содержимое `../../LICENSE-GPL` без завершающего перевода строки. Это не обычный текстовый файл mode 100644. При материализации и проверке необходимо сохранить реальную symlink, иначе существующий [check_licenses.py](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/scripts/check_licenses.py#L49) справедливо откажет. Checker не запускался.

Release source archive использует [git archive HEAD](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/scripts/release.py#L124); изменения должны быть отдельным проверенным commit в разрешённой рабочей копии, не «грязным» неучтённым source overlay. Ни source snapshots, ни release provenance не подменяются.

## Состав точного кандидата и проверка

- 3 побайтных rename;
- новый Cargo.toml и GPL symlink;
- 3 изменённых файла: root Cargo.toml, Cargo.lock, src/main.rs;
- 23 добавленных и 2 удалённых строки вне неизменённых переносов;
- patch привязан к Desktop `50f8b53b686816e7e32b89901aa6ed399826fb37`; другие версии требуют повторной проверки.

Сделано только чтение через GitHub connector и преобразование/сравнение строк в памяти. Pure JavaScript replay проверяет, что unified-text patch даёт ровно указанные overlay bytes/modes; это **не** `git apply --check`. Все 8 test bodies сохранены, но ни один Rust-тест не выполнен.

NOT_RUN: git apply, TOML/Cargo validation, rustfmt, Cargo metadata/tree/check/build/test, license checker на файловой системе, native/UI, packaging, CI. Independent extraction source review: CLEAR для точного patch; это не проверка controller или его исполнения.

До публикации: независимая проверка точного patch/overlay/default-members/lock/license и разрешение root. До применения/исполнения: отдельное разрешение соответствующего этапа. Этот кандидат не обходит ранее отклонённую native fixture, не затрагивает tooltip, DCP, PR37, PR38, upstream или main.

## Узкая hosted qualification: что делает controller

`qualify_diff.py` через общий `../pure_crate.py` предназначен только для отдельного одноразового checkout, а не рабочей копии пользователя. Он **изменяет index и working tree этого checkout**, применяя один проверенный patch; не создаёт commit, не делает push и не меняет upstream. Не запускайте его без отдельного разрешения на этот этап.

1. Проверяет exact Desktop commit и original tree, чистый checkout, SHA256 patch.
2. Выполняет `git apply --check`, затем `git apply --index`; `git write-tree` должен дать reviewed candidate tree `c8f4f639f5d355c4c165086f68ace743ac49b84c`. Проверяет working tree против index, SHA256 всех 8 overlay файлов, удаление трёх старых путей, настоящий GPL symlink, manifest/default-members/release.
3. Создаёт новый target directory вне source checkout. Старые сборки не чистятся и не используются. Проверяет pinned Rust; compiler/profile overrides из перечисленных controller guards не принимаются. Это provenance-check для контролируемого hosted workflow, **не sandbox** и не общий безопасный запуск произвольного окружения.
4. Выполняет единственный Cargo test invocation:
```sh
cargo +1.95.0 test --locked -p proteus-diff --lib --jobs 2 --color never --message-format=json -- --test-threads=4 --color never
```
5. Проверяет весь captured Cargo JSON и libtest transcript: package identities только `proteus-diff` + 7 закреплённых serde closure packages; ожидаемые source/target identities; один успешный build-finished; один diff library test executable внутри нового target; единственный Cargo Running unittests header с тем же executable и единственный running 8 tests header; ровно 8 уникальных ожидаемых test names, все `ok`; итог 8 passed, 0 failed/ignored/measured/filtered.
6. Записывает run_id/run_attempt/workflow_ref/job, observed features/profile/fresh для artifacts, SHA256 и размер реально запущенного test executable, SHA256 лога, toolchain, controller/config/patch identities, exit code и wall time. Повторно проверяет source hashes, рабочее дерево и exact index tree через git write-tree. Полный lockfile не урезается и не регенерируется.

Artifacts с `fresh: true` тоже учитываются. Проверяется **selected compiler artifact closure**, а не отсутствие native/GPUI/Core во всём workspace metadata: в общем workspace они законно остаются. До Cargo scope ограничен exact source tree и manifest; после Cargo проверяется фактическая evidence. Это не обещание остановить произвольный неизвестный compiler до выполнения — источник уже должен совпасть с reviewed tree.

Новый test executable — обычный скомпилированный Rust unit-test процесс. Он не является native Desktop binary или ранее отклонённой native fixture. В workflow нет запуска GPUI, окна, Core, расширений, `scripts/test.py`, `portable.py` или каких-либо старых native fixtures. Native callers и обе оставшиеся UI/widget проверки **не квалифицированы** этим gate.

### Время и ресурсы

Один job, Cargo jobs 2, libtest threads 4, Cargo timeout 900 секунд, workflow timeout 20 минут. Перед toolchain setup и controller — минимум 8 GiB свободного места; controller требует одну файловую систему source/output и проверяет low-water 2 GiB каждые 0,25 секунды во время дочерних команд. Общий bounded runner использует новую process group, сохраняет до 8 MiB raw output и в finally убивает всю группу, даже если Cargo уже завершился, а потом ожидает leader не более 10 секунд. Timeout/output/disk/reap limit дают FAIL с partial log; автоматического повторного запуска нет. Caps: 64 compiler artifacts, 1 MiB на проверяемый source file, 64 MiB test executable, 256 KiB receipt. Эти resource-ветки проверены чтением, но не исполнением. Coordinator допускает ветку только при свободном общем лимите активных source jobs; concurrency этого workflow не заменяет общий лимит. Новый target исключает путаницу со старыми артефактами; target cache пока отсутствует. Ничего не обещаем про cold или warm ускорение до реальных измерений.

Общий workspace/lock всё ещё содержит остальные packages. Cargo даже при `-p proteus-diff` может получать Git/index metadata для workspace resolution, включая закреплённый contracts source. Из выбранного compile graph это не делает GPUI зависимостью, но может заметно увеличить first-run network/time. Мы не вырезаем root manifests, patches, Git pins или lock entries ради красивого времени. `cargo_wall_seconds` включает resolution/fetch, compile/link и test execution вместе; это не отдельно измеренное время компиляции и не runtime/RAM shipping-клиента.

### Evidence и отказ

`result.json` имеет PASS только после всех source/graph/test/post-source проверок. На ошибке сохраняет FAIL, stage, error type, Cargo exit code/timeout при наличии и captured log. Отсутствующий receipt, прерванный job или провал setup не являются PASS. Несовпадение source/tree/package/test identity — qualification failure, а не разрешение ослабить gate или повторить denied native route. Никакого автоматического retry, удаления данных или fallback на полный runner.

`test_qualify_diff.py` содержит 14 авторских synthetic transcript tests; они не исполняют upstream код, Cargo или subprocess. Их 14 test bodies прошли AST-extracted проверку в памяти. Оба полных Python source прошли ast.parse; выполнены только package_key/inspect_output, synthetic helpers и тела case methods. В текущей tabs-ветке setUp проверяет только pure configuration; mock/global substitution не используется. Controller import/top-level, file-based CLI, bounded runner, filesystem/network/product code не исполнялись при private AST-проверке. Вместо Path.resolve в parser используются pure lexical paths; реальная symlink normalization и containment выполняются позже controller и пока NOT_RUN. Они проверяют позитивный complete/fresh transcript и reject случаев чужого package/source/version/target, неполных или дублированных tests/artifacts, ignored/filtered/failure, отсутствующего build-finished и неизвестного JSON. Дополнительно отклоняются отсутствующий/чужой execution header, неправильный count header и избыток artifacts. Эти parser tests не подменяют реальные 8 Rust-тестов.

## Публикация и запуск — отдельный допуск

Исходный PR41 содержал ровно 6 additive файлов: этот README, extraction patch, expected.json, controller, synthetic tests и `.github/workflows/check-desktop-diff-crate.yml`. Это исторический состав PR41, не состав новой tabs-ветки с общим runner.

Предложенная ветка — `ci/desktop-diff-crate-20261027` в личном `Qweasd123tg/proteus-modules-dot`. Workflow запускается **только push на эту точную ветку** при изменении своей папки/файла workflow; job повторяет repository/ref/event guards. Нет pull_request trigger, матрицы или изменения существующих workflows. Публикация этой ветки запрашивает hosted выполнение, поэтому source-only разрешения на публикацию документации недостаточно: root отдельно проверяет final independent review и активные jobs перед разрешённым push.

Action revisions закреплены по существующему проверяемому workflow личного main; checkout не сохраняет credentials, permissions contents: read. Hosted setup ставит только lld и pinned Rust, без Desktop GUI/system dependency набора. Artifact name привязан к run_id/run_attempt/delivery SHA; upload сохраняет только result.json и bounded raw логи, не target directory и не бинарники.

Extraction patch SHA256: `f52ad869157c095710ffc1eb0325ab7311c1b117e1aa07aedb520054b92a859f`.
Independent extraction review SHA256: `5792e9d5809df0e2f5e313e851841dd3afdef88f8ed6f1d9d43cbf80daae1942`.
Файл expected.json — зафиксированные ожидания на момент подготовки; его NOT_RUN не обновляется скрыто после запуска. Фактический результат находится в отдельном immutable run artifact/receipt и должен быть привязан к delivery commit.

До отдельного review/допуска: file-based imports/CLI/runner, git apply, Cargo, compiled unit executable, workflow и publication — **NOT_RUN**. Shipping build/UI/portable/runtime/RAM остаются **NOT_RUN / NOT_MEASURED**, даже если будущий pure gate станет PASS.
