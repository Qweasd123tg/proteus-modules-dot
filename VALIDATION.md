# Воспроизводимая проверка трёх примеров

Требуются Python **3.11+**, `rustup` и уже установленный официальный Rust/Cargo
**1.95.0**. Для полной проверки также нужен `rustfmt` этой toolchain. Локальный
runner ничего не устанавливает, не меняет default toolchain, не очищает кеши и
не запускает исходники или тесты исследованных сторонних проектов. Cargo может
скачать закреплённые зависимости и выполнить их обычные build steps.

Из корня пакета:

```sh
python3 -I scripts/test_check_examples.py
python3 -I scripts/check_examples.py
```

Результат: [`validation/results.json`](validation/results.json), подробности:
`validation/logs/`. Коды завершения: **0 — всё прошло**, **1 — ошибка**,
**2 — проверка неполная**. Отсутствующие инструменты, непрошедшие prerequisites,
нулевое число Rust tests и ignored tests не превращаются в положительный результат.
Каждый запуск записывает фактически выполненные команды, статусы, test counts,
хеши manifests/locks, исходников, fixtures/config, самого runner и собранных
executables; итог сохраняется также при ошибке. Изменение source/config/test bytes
во время проверки делает итог ошибкой, а не stale pass.
Нормализованные пути не содержат локальные workspace/toolchain directories.

Поддерживается общий `CARGO_TARGET_DIR`; относительный путь разрешается от каталога
запуска runner один раз. `CARGO_HOME` и `RUSTUP_HOME` наследуются без постоянных
изменений окружения. Допустимы `--root PATH`, `--report PATH` и `--timeout SECONDS`.
Рекомендуется отдельный target для каждого одновременно работающего validator.
Выбор произвольных проектов, shell-команд или дополнительных Cargo arguments
не предоставляется. Каждый из трёх manifests и locks должен указывать официальный
SDK commit `3f36a003b4f3fde2242fc80f7aedac00dd127d1d` без path/branch/tag overrides.

## Что действительно запускается

Для каждого самостоятельного workspace: `cargo test --locked`,
`cargo build --locked --message-format=json` и `cargo fmt --all -- --check` через
`rustup run 1.95.0`. Binary path берётся из compiler artifact, а не угадывается по
`target/debug`. Проверяется dev/test profile, не optimized/release profile.

* **Hermes:** существующий `tests/wire.rs` уже запускается в `cargo test`;
  повторного запуска той же suite нет. Receipt fixtures синтетические: они не
  утверждают, что внешний verifier действительно выполнил проверки.
* **Letta:** существующий `tests/wire.rs` также запускается один раз в `cargo test`.
  Это реальный executable с синтетическими host frames, не полный Core assembly.
* **Pi:** `scripts/smoke_pi_wire.py` запускает только собранный Pi executable и
  проверяет 14 wire/advisory/error cases напрямую. `examples/pi-ready-steps/smoke.py`
  с внешним Core conformance CLI в автоматическую проверку не входит и повторно
  не запускается. Его дополнительный ручной результат следует документировать
  отдельно, без подмены отсутствующей проверки положительным статусом.

Это не проверка реальной модели, OS sandbox, live tool execution, profile assembly,
настоящих verification receipts или end-to-end in-flight cancellation/concurrency.
Все статусы и границы относятся к конкретному сохранённому запуску, не обещают
корректность будущего коммита или внешней host-конфигурации.

## CI

`.github/workflows/check-examples.yml` использует только GitHub-owned actions,
закреплённые на immutable commit SHA. Проверено чтением официальных Git refs и
`action.yml` на этих commits **2026-10-25**:

* [actions/checkout, `11d5960a…`](https://github.com/actions/checkout/blob/11d5960a326750d5838078e36cf38b85af677262/action.yml)
* [actions/upload-artifact, `ea165f8d…`](https://github.com/actions/upload-artifact/blob/ea165f8d65b6e75b540449e92b4886f43607fa02/action.yml)

CI явно устанавливает Rust 1.95.0 и rustfmt лишь в ephemeral GitHub runner.
Права — `contents: read`; credentials не сохраняются checkout action. Нет secrets,
`pull_request_target`, cache action, push/merge/deploy или автоправок исходников.
В artifact попадают только `validation/results.json` и `validation/logs/*.log`,
не исходные snapshots, toolchain, target или файлы из исследованных проектов.
Наличие workflow-файла не означает, что удалённый CI уже запускался или прошёл.
