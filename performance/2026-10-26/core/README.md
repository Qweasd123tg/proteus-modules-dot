# Proteus Core: восстановление read-index и blocking startup

Источник: https://github.com/Proteus-harness/Proteus-core
Базовый commit: `7435f2a6d90e532665ebed4da67526b609158fc8`.
Пакет предназначен только для отдельной папки
`Qweasd123tg/proteus-modules-dot/performance/2026-10-26/core/`.
Это переносимые patches исходников Core, не изменение реализации модулей.

## Применение

На отдельном checkout указанного commit (не на почти заполненном локальном диске):

```sh
git apply --check /path/to/0001-tests.patch
git apply --index /path/to/0001-tests.patch
# Контроль baseline: ожидается behavioral FAIL существующего test, не ошибка компиляции.
python3 scripts/test.py -p proteus-core --lib paged_snapshot_full_history_and_revision_checked_pages_agree -- --nocapture

git apply --check /path/to/0002-fix.patch
git apply --index /path/to/0002-fix.patch
cargo fmt --all -- --check
python3 scripts/test.py -p proteus-core --lib app_server::
git diff --check
```

Первый patch расширяет существующий HTTP/session test и добавляет unit-file.
Новый unit-file включается через `mod tests` только вторым patch, поэтому
baseline-компиляция не зависит от ещё не добавленных production helpers.
Runner готовит reference-module fixture из pinned Modules
`7fceaebc3bed8add9b0e3091110f59deca86ba46`.
Он не запускает живые model API. Нужны Rust 1.95.0, Python3 и обычные
Core build dependencies; использовать текущие инструкции upstream runner.
Модульные исходники, contracts, CI triggers, release и deployment не меняются.

## Поведение и инварианты

- Cache hit сохраняет прежний путь, в том числе завершённую старую revision
  во время append нового turn.
- Cache miss делает одну строгую canonical projection. Явная revision должна
  совпасть с fingerprint источника до чтения; fingerprint проверяется снова после.
- Потерянная старая revision не восстанавливается из нового journal под старым id.
- Cache write best-effort: проверенные in-memory rows возвращаются и при отказе
  установки индекса. Нет бесконечного retry, writer lease или canonical writes.
- SQLite tail read startup перемещён внутрь уже существующего blocking worker.
- При rebuild `base=None`: связь с потерянной display-проекцией не выдумывается.

## Targeted evidence

Baseline test:
`app_server::http::tests::session_reads::paged_snapshot_full_history_and_revision_checked_pages_agree`

Новые reachable после fix unit tests:
- `app_server::read_model::tests::history_recovery_covers_empty_short_and_exact_page_boundaries`
- `app_server::read_model::tests::history_recovery_never_relabels_new_source_as_a_lost_revision`
- `app_server::read_model::tests::history_recovery_does_not_hide_corrupt_canonical_source`

HTTP regression независимо повреждает индекс перед full-history и page reads:
missing, malformed SQLite, invalid payload checksum, directory blocking rename.
Проверяется полное равенство DTO, revision, positions и неизменность journal.
Unit tests покрывают 0/1/49/50/51/100/121 строк, старый действительный cache при
append, отказ потерянной старой revision и отказ повреждённого canonical source.
Существующий `app_server::tests::startup` остаётся regression suite для
fresh/stale resume; перенос I/O в blocking worker дополнительно проверен review,
но отдельного runtime scheduling/timing доказательства пока нет.

## Статус проверки

- Выполнено локально: чтение pinned AGENTS/testing instructions, source review,
  форматирование изменённых Rust через установленный rustfmt 1.95.0 без сборки.
- Cargo compilation/tests, baseline-failure и corrected-pass ещё НЕ выполнены.
- Performance timings и native GUI не измерялись; ускорение в процентах не заявляется.
- Source blob SHA и hashes patches перечислены в provenance.json.

Дополнительно: оба patches разобраны `git apply --numstat`; каждый hunk
сверен в памяти с pinned connector source и восстанавливает ожидаемые bytes.
Независимый static review (`review_speed_patch_safety`) завершён без замечаний
к этим hashes. Это не заменяет Cargo compile/test evidence.
