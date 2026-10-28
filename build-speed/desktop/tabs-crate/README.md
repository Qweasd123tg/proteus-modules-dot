# Desktop: 38 тестов модели вкладок без GPUI

**Подготовлено для отдельного draft review.** Move-only extraction прошёл независимый source review. В private AST-проверке прошли 26 авторских synthetic сценариев: прежние 14 для diff и 12 для tabs/configuration. Настоящие 38 Rust tests, file-based imports/CLI и новый hosted workflow пока **NOT_RUN**. PASS прошлого PR41 относится только к его неизменённому head, не к этому shared runner.

## Польза и точная граница

[Чистая модель src/tabs](https://github.com/Proteus-harness/Proteus-desktop/tree/50f8b53b686816e7e32b89901aa6ed399826fb37/src/tabs) становится GPL library `proteus-tabs`. Переносятся 16 файлов / 2 604 строки / 89 422 байта, побайтно без изменений, включая 38 tests. Не меняются persisted schema, алгоритмы, поля, visibility или 24 прямых caller-файла. `mod tabs;` в main заменяется на `use proteus_tabs as tabs;`.

Отдельный [src/ui/tabs renderer](https://github.com/Proteus-harness/Proteus-desktop/tree/50f8b53b686816e7e32b89901aa6ed399826fb37/src/ui/tabs) остаётся native. Source review не нашёл private/pub(super), inherent/orphan impl или обратных dependency blockers во всех 250 Rust-файлах; это **не проверка native-компилятором**.

Цель — не заставлять Cargo компилировать native/GPUI test target только ради модели вкладок. Это реальная граница пакета, а не фильтр тестовых имён внутри прежнего native binary. Выигрыш shipping build time, runtime или RAM здесь **не измерен**.

## Последовательность исходников

1. Upstream Desktop commit `50f8b53b686816e7e32b89901aa6ed399826fb37`, tree `6d873806bcf78f8f95169bf2294434f168179504`.
2. Неизменённый [diff patch](../diff-crate/extract-diff-crate.patch): SHA256 `f52ad869157c095710ffc1eb0325ab7311c1b117e1aa07aedb520054b92a859f`; tree после него `c8f4f639f5d355c4c165086f68ace743ac49b84c`.
3. [Tabs patch](extract-tabs-crate.patch): SHA256 `30d5fe6ef1b404429ec46086b4ab343db2e3ef5291bc494bef257add15fdbfdd`; composed tree `99dc8e02b8acd3aba3943ffdf2c0dad441bb9016`.

Второй patch не предназначен для применения прямо к upstream. Controller проверяет входной и выходной index tree **каждой** ступени; одно совпадение финального текста недостаточно.

Оба GPL symlink сохраняются как Git mode **120000** с точными 17 байтами `../../LICENSE-GPL`, без LF. Zed attribution headers history.rs и pane.rs не изменяются. Не переносить этот код в Apache client-common.

## Команда компонента и общий охват

После отдельного разрешённого применения обоих patches, из корня Desktop:
```sh
cargo test --locked -p proteus-tabs --lib --jobs 2 -- --test-threads=4
```
Такого пакета ещё нет в исходном upstream. Для focused unit tests нужны закреплённый Rust 1.95.0, выбранные зависимости и Linux lld из upstream .cargo/config.toml, но не подготовленные app-server/extension binaries или окно.

В [expected.json](expected.json) зафиксированы все 38 точных имён:
- root: 6;
- history: 6;
- pins: 4;
- sizes: 12;
- tree: 10.

`default-members = [".", "crates/diff", "crates/tabs"]` сохраняет обычный root cargo test плюс 8 diff и 38 tabs tests. Явный `-p proteus-native` больше не содержит перемещённые tests. Полный поддерживаемый [scripts/test.py](https://github.com/Proteus-harness/Proteus-desktop/blob/50f8b53b686816e7e32b89901aa6ed399826fb37/scripts/test.py) не изменён: он использует --workspace и заранее готовит реальные расширения. Это другой, более широкий gate.

Production dependency нового crate — serde с derive; serde_json только dev-dependency. Все прежние registry pins/checksums сохраняются. В Cargo.lock добавлены local tabs package и native → tabs edge; 862 прочих прежних blocks дословно прежние.

Ожидаемый выбранный compiler graph: local tabs + 11 registry packages — serde, serde_core, serde_derive, proc-macro2, quote, syn, unicode-ident, serde_json, itoa, memchr, zmij. До hosted запуска это **source inference**, а не Cargo observation. Workspace resolution может fetch metadata Core и иных пакетов; отсутствие GPUI/Core требуется в выбранных compiler artifacts, не во всём metadata. Общий lock/root manifests не вырезаются ради красивого времени.

## Один общий runner, без смены global state

[../pure_crate.py](../pure_crate.py) — единственный engine, 440 строк; он получен ограниченным изменением прежнего 372-строчного runner. Блок process-group/resource handling и require_git перенесён без изменения байтов.

Два 12-строчных fixed wrappers выбирают только свою reviewed configuration. CLI принимает лишь --source и --output, не произвольный package/target/config. Фиксированный parent import path не используется для подмены engine globals. Нет второй копии большого runner или dynamic native loader.

Configuration содержит component identity/manifest/default-members, exact test identities, registry pins, source hashes/modes и упорядоченные patch stages. Diff regression восстанавливает **в точности старые config bytes** SHA256 `930e2305a62b378b371411b9eea741d9f82ca96a195dd58dcf0be080517166fa` и повторяет его 8 synthetic test identities.

Будущий controller:
1. Проверяет exact clean Desktop HEAD/tree, configuration и оба patch SHA/tree stages; применяет их только в disposable checkout.
2. Проверяет все 26 composed overlay files, 19 удалённых путей, manifests, GPL symlink, default-members и неизменённый release profile.
3. Создаёт новый target вне source, проверяет pinned Rust и запрещённые compiler/profile overrides.
4. Запускает ровно одну Cargo-команду:
```sh
cargo +1.95.0 test --locked -p proteus-tabs --lib --jobs 2 --color never --message-format=json -- --test-threads=4 --color never
```
5. Проверяет selected package/source/target identities, единственный libtest executable и совпадающий Running unittests header, running 38 tests, все 38 уникальных ожидаемых ok и summary без failed/ignored/measured/filtered.
6. Проверяет final source/index tree повторно. Receipt связывает delivery/run/attempt/workflow/job, shared engine SHA, wrapper SHA, config SHA, обе patch SHA/tree stages, actual features/profile/fresh, binary SHA/size, bounded log SHA и elapsed time.

Реальный test executable запускается самим Cargo. Это обычные Rust unit tests модели, не native Desktop binary. Нет GPUI/UI, Core binary, полного workspace runner, portable или ранее отклонённой native fixture.

## Ресурсы, evidence и предел PASS

Один job; Cargo jobs 2; test threads 4; Cargo timeout 900 s; workflow 20 min. Admission 8 GiB, low-water 2 GiB, контроль во время дочерних команд каждые 0,25 s; source/output должны быть на одной monitored filesystem. Fresh target без cache/удалений. Process group завершается целиком при выходе/ошибке, leader reaped с пределом 10 s. Caps: 8 MiB raw output, 64 compiler artifacts, 1 MiB/source file, 64 MiB test executable, 256 KiB receipt. Partial log и FAIL сохраняются при предусмотренных resource failures; setup failure/отсутствие receipt не равны PASS. Resource/failure branches пока проверены только source review, не stress execution.

Workflow имеет только push trigger для `ci/desktop-tabs-crate-20261027` и соответствующих paths, плюс повторный repository/ref/event guard. Нет pull_request trigger или matrix. Остальные 18 workflows не редактируются и не подходят по branch/path. Их старые branches не перемещаются. Checkout/upload actions закреплены; credentials не сохраняются; только contents: read. Artifact содержит receipt и text logs, не binaries/target. Общий лимит двух активных source jobs проверяет coordinator отдельно; workflow concurrency не заменяет этот лимит.

26 private controls выполнены только через AST-selected authored pure functions/classes в Python -I -B: stdlib и synthetic data, без импорта/запуска самого controller module, top-level, файловых операций, network, subprocess или upstream кода. Импорт wrappers, file-based unittest discovery, Git apply, Cargo и workflow этим не проверены. Будущий hosted шаг обязан сначала повторить обе группы controls.

UI motion, startup/server/session integration, document-id invariant, preferences integration, focus/drag/drop/keyboard, native caller compilation и shipping build остаются **NOT_RUN**, даже если pure tabs gate позже PASS.

## Shipping performance не подменяется

Для измерений клиента сохраняется:
```sh
cargo build --release --locked -p proteus-native --jobs 2
```
Это не команда данного hosted gate. Release остаётся opt-level 3 / ThinLTO / codegen-units 1 / strip true; dev/fast profile text также прежний, --fast не удалён. Новая crate/type identity может изменить inlining, monomorphization и binary; generic closure methods могут всё ещё инстанцироваться у native consumer. Native relink/ThinLTO сохраняются. В fast перенесённый код наследует CGU16 вместо прежнего native override CGU256.

Runtime/RAM, release binary equivalence и относительное ускорение сборки — **NOT_MEASURED**. Cargo wall time включает resolution/fetch/compile/link/tests вместе; его нельзя назвать временем компиляции или runtime benchmark. Ни прежний diff PASS, ни будущий tabs PASS не закрывают native integration.

Публикация, hosted run и изменение любых upstream/main/старых PR этим документом не разрешаются. До отдельного exact review и допуска root новый gate остаётся private/NOT_RUN.
