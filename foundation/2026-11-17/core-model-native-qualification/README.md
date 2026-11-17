# Нативная квалификация Core model candidates #167 + #171

Дата: 2026-11-17. Обе опубликованные source-only proposals проверены вместе на
точной базе Core `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`. Живой `main`
совпадал с ней до и после прогонов. Delivery snapshot:
`fd8f893314f22ce591921293cb7384cc6f1737c1`.

Это новый результат, а не исправление старых свидетельств: исходные README,
CHECKS и source-only утверждения #167/#171 сохранены. Upstream, consumer pins,
поставляемые бинарники, активные workflows и конфигурация пользователя не менялись.

## Результат

- На неизменённом production-коде с четырьмя предложенными test methods:
  **11 PASS, 2 FAIL**, причём упали именно два ожидаемых regression cases.
- С обеими production patches вместе и только форматными исправлениями:
  **13 PASS, 0 FAIL** в двух config-only Rust libtest фильтрах.
- Все пять изменённых файлов проходят Rustfmt. Core `git diff --check` проходит.
- Cargo.lock сохранён побайтно; весь код компилировался с `--locked --offline`
  после успешного обычного `cargo fetch --locked`.
- Combined patch прошёл strict apply в отдельной baseline-копии, сравнение всех
  пяти candidate files и reverse с точным восстановлением исходных байтов.

### Красная база

`core::config::models::tests`: 7 PASS, 1 FAIL. Новый
`inline_role_choice_resolves_in_its_child_catalogue` падает с
`unknown model alias "child-only"`.

`app_server::config_builder::tests::model_names`: 4 PASS, 1 FAIL. Новый
`file_include_model_edits_remain_reloadable_without_rewriting_base` падает на
первой комбинации `toml/model/models`: после Save загрузка получает одновременно
`model` и `active_provider`.

Это фактические Rust failures, не Python-эмуляция. Два дополнительных контроля
#171 проходят и на базе: неизвестный внешний alias по-прежнему отклоняется,
а child shadowing не меняет parent choice.

### Зелёная совместная версия

Те же фильтры дают соответственно 8 и 5 PASS. Compound test #167 полностью
прошёл 8 комбинаций формата/choice key/catalogue key, 24 последовательных
Save→reload и 16 отказов с сохранением байтов. Это внутренние шаги одного
native test method, а не ещё 48 независимых tests.

Исходные patches потребовали только Rustfmt переносов в трёх файлах. В
`combined-formatted.patch` нет иных изменений сверх #167/#171. Он заменяет
повторное применение трёх исходных patch artifacts, а не накладывается на них.
Исходные и итоговые hashes приведены в `CHECKS.json`.

## Команды и инструменты

Rust установлен с официального `static.rust-lang.org`: rustup-init binary
сверен с опубликованным SHA-256, удалённый shell script не исполнялся.
Rust/Cargo 1.95.0 соответствуют rust-toolchain.toml Core и Modules;
Rustfmt 1.9.0, Clippy 0.1.95. Bundled LLVM LLD 22.1.2 удовлетворяет существующему
`.cargo/config.toml` без изменения этого файла. Полные версии: `logs/toolchain.txt`.

Установка дополнительно прошла отдельный dependency-free offline smoke:
компиляция, 1 unit test, fmt и Clippy с запретом warnings. Этот smoke не входит
в число 13 project tests.

В обеих фазах использовались точные команды:

```sh
CARGO_BUILD_JOBS=2 cargo test --locked --offline -p proteus-core --lib \
  core::config::models::tests -- --test-threads=2
CARGO_BUILD_JOBS=2 cargo test --locked --offline -p proteus-core --lib \
  app_server::config_builder::tests::model_names -- --test-threads=2
```

Код обоих выбранных модулей прочитан перед запуском: нормализация конфигурации,
load/save временных файлов, без запуска declared workers или сетевых клиентов.
Компиляция Core build.rs читает только Git metadata. Обычный `scripts/test.py`
не запускался: он готовит process fixtures и выходит за разрешённый scope.
Следовательно это scoped native qualification, не прохождение штатного полного gate.

## Оставшиеся ограничения

- **Workspace `cargo fmt --all --check` FAIL уже на исходной базе**: порядок
  `mod session_selection` / `mod session_model` в `app_server.rs`. После правок
  результат тот же, несвязанный исходный дефект не исправлялся. Логи сохранены.
- Core libtest выдаёт два исходных dead_code warnings для `Polling::controlled`
  и `Poll::controlled`; они не исследовались и не менялись.
- #167 намеренно отклоняет очистку inherited selection и изменение inherited
  catalogue. Это bounded restriction, не полная поддержка config editing.
- Local-only-choice с unrelated includes не добавлен отдельным native контролем.
  Concurrent include mutation и transactional snapshot guarantees не проверены.
- Project process/HTTP fixtures, полный runner, приложение, UI, hosted CI и
  benchmarks **НЕ ЗАПУСКАЛИСЬ**. Нет вывода о production readiness, performance
  или исправлении всех source-ownership случаев.

## Файлы

- `combined-formatted.patch`: оба исправления и четыре предложенных test methods.
- `CHECKS.json`: exact refs/hashes, counts и patch roundtrip.
- `logs/`: red/green outputs и formatter evidence; только локальный абсолютный
  путь checkout заменён на `<CORE_CHECKOUT>`, assertions и результаты не изменены.
- `SHA256SUMS`: контрольные суммы нового пакета.
