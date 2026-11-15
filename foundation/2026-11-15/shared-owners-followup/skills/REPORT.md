# Skills CI: один существующий владелец вместо четырёх копий

Это реализованный и локально проверенный кандидат продолжения плана #165,
не новая находка и не применение к active CI. Exact delivery base:
`cbd9ec315f88f85708d26d47cc2193970a7c904b` (#165 merged).

## Изменение

`current-core-skills/ci/run.sh` непосредственно использует четыре уже
существующих owner-файла из `core-skills/ci`: probe, result verifier и две
Python test suites. Его дубли удалены, без wrappers, registry или нового
runner framework. Canonical verifier controls принимают optional путь к
scenarios; current lane передаёт свой `scenarios.json` явно. Старый default
для core-skills сохранён.

Probe, result verifier и capture controls остаются побайтно прежними. Все
11 verifier test methods сохраняют прежние AST; изменяется только источник
scenario fixture в setUp и CLI выбор этого источника. Разные Core pins,
Rust inputs, eleven Core checks и artifacts двух compatibility lanes не
объединяются. Обе линии по-прежнему исполняют все 15 Python controls.

Итог patch: **15 файлов, +79/−355, net −276 строк** с README, workflows и
hash manifests. Убраны 333 строки четырёх дубликатов, в том числе 15 повторных
test definitions. Это не удаление 15 проверяемых behaviors и не сокращение
числа обязательных CI executions. Измеренного ускорения CI/runtime нет.

## Closure и исторические результаты

Current source manifest читает и сверяет четыре реально используемых owner
файла с `ci/shared-ci.sha256`. Сам этот manifest и checker входят в active
`CODE.sha256`. Проверки происходят до gate и после probe, а before/after
verifier сравнивает полный объект, включая `shared_ci`. Отдельный lock-only
post-resolution check также сверяет shared files, исключая только допустимое
изменение harness Cargo.lock. Удаление owner-файла
или изменение любого из четырёх источников отклоняется.

Current workflow и его package copy синхронно получили trigger на owner CI
и четыре дополнительных envelope inputs: всего 9, ниже existing MAX_INPUTS=16.
Hash-проверка всего gate остаётся на месте. Изменение shared owner требует
обновить current shared freeze, иначе gate намеренно откажет.

`CODE.sha256` обновляется как **active source freeze**, не как переиздание
старого запуска. `validation/`, `RESOURCE-OVERLAY.json`, прежние result/source
snapshots, `VALIDATION.md`, dependency/source pins и Cargo inputs не меняются.
README явно отделяет active revision от исторических attestations. Патч
в delivery artifact не меняет active source tree автоматически.

## Важная граница совместимости

Проверенный entrypoint `ci/run.sh`, CLI аргументы probe/verifier, cwd, scenario
pin и результаты для штатного repository layout сохраняются. Но current lane
теперь требует sibling `core-skills/ci`: копия только current-core-skills уже
не self-contained. Четыре прежних private script paths исчезают. **Это не
безусловная эквивалентность всех способов копирования/прямого запуска.**

Поэтому предлагается публиковать patch как reviewed candidate, а не молча
переключать active workflows. Если самостоятельное копирование current
package является поддерживаемым delivery contract, сначала нужен явный
packaging вариант с included shared owner; копировать обратно четыре
реализации или добавлять fallback shims ради обхода этой границы не стоит.

## Что реально выполнено

Python 3.12.14, 37 CLI outcomes: **27 exit 0 + 10 ожидаемых отказов = 37/37**.
Это не 37 product tests. Восемь suite runs дали **60 успешных method executions**:
15 unique methods × baseline/candidate × два compatibility lanes. Или 30
executions baseline и 30 candidate. Пропущенных cases нет.

- Existing capture controls исполнили маленькие authored Python child strings:
  stdout/stderr, overflow/reap, timeout/reap и malformed UTF-8.
- Existing verifier controls выполнили все 11 methods для каждого lane.
- Active freezes и настоящие source_manifest CLI прошли на обоих trees.
- Отдельные copies отклонили изменение каждого shared файла и его отсутствие;
  восстановленный manifest прошёл.
- Verifier CLI принял два synthetic reports с собственными pins и отверг оба
  crossed-pin варианта; изменение shared before/after attestation отклонено.
- Exact Python post-resolution block из `lock_only.sh` прошёл на unchanged
  inputs и при разрешённом Cargo.lock-only изменении, но отверг изменение
  shared verifier. Сам shell script и Cargo не исполнялись. Это исправление
  найденного независимым reviewer пропуска shared closure; первый candidate
  и его 34-outcome result superseded, не финальная квалификация.
- Probe `--help` побайтно совпал; лишние scenario args отклонены; `bash -n`
  прошёл. Ни help, ни shell parsing не запускают product gate.
- Все 61 исходных Git blobs сверены с exact fresh tree; strict whitespace
  apply-check, применение, полное совпадение materialized candidate и reverse
  до исходных bytes независимо повторены reviewer.

Независимый reviewer прочитал source и точный driver до запуска, затем raw
stdout/stderr и outcome JSON. См. [REVIEW.md](REVIEW.md). Public package не
содержит полных source snapshots или raw logs. `validate.py` воспроизводит
этот bounded check при подготовленных `before/` и `candidate/` деревьях.

**NOT RUN:** Rust/Cargo/rustfmt, actual Core probe, package `ci/run.sh`,
resource-envelope runtime, full CI, native UI/provider и performance.
Synthetic verifier reports не утверждают, что Rust checks исполнялись.
До active adoption нужен exact-head affected CI; пустые GitHub checks не
являются PASS. Upstream Proteus и пользовательская установка не изменены.
