# Однократная проверка общей test fixture

Свежая delivery base: `99b88e2dd2be8d38a2d407756cfd903ed49de990`.
После тестов повторный fetch подтвердил тот же main. Локальный кандидат;
этот worker не публиковал изменения.

## Конкретное изменение

В `build-speed/desktop/diff-crate/test_qualify_diff.py` общий JSON fixture
проверяется один раз сразу после чтения вместо `setUp` каждого метода.
Diff: **+1/−3 строки**. Новых helpers, frameworks, тестов, production-изменений,
workflow-изменений или удалённых assertions нет.

Собственная граница parser `inspect_output` по-прежнему вызывает
`validate_expected` при каждом вызове. Просто удалить setup check было бы
неправильно: invalid fixture могла бы удовлетворить `assertRaises` раньше
ожидаемой ошибки transcript. Одна проверка при загрузке сохраняет отказ даже
при выборе одного negative test. Диагностика переносится из setup error в
import/discovery error; ни один вариант не превращается в ложный PASS.

## Реально выполненные проверки

Python 3.12.14. Обе существующие pure suites выполнены до и после:
14 diff +12 tabs/configuration methods, все PASS без skips. Это
**26 уникальных методов и 52 executions**, не 52 уникальных tests.
Локальный observation driver считал вызовы, не подменяя production functions,
и запрещал вход в controller/command/qualification paths.

- Diff validation calls: **41 → 28**. Fixture validations: 14 → 1;
  parser-boundary validations остаются 27.
- Tabs validation calls и outcomes не изменились.
- Общая EXPECTED fixture осталась побайтно эквивалентной после каждой suite.
- AST всех 14 diff test methods не изменился.
- Selected negative case с valid fixture проходит до/после; invalid schema
  отклоняется setup до и import после. Эти четыре oracle outcomes учитываются
  отдельно от full-suite executions.
- `git diff --check`: PASS. Изменён только указанный test file.
- Independent reviewer повторил 14 diff methods и selected-fixture oracle;
  ACCEPT. Его повтор не увеличивает число уникальных tests.

Это небольшая чистка сопровождения, не заявленное заметное ускорение.
Cargo, Rust product tests, native UI, hosted CI, controller/process paths и
benchmarks НЕ запускались. Historical receipts/freezes не менялись.

## Active adoption: source freeze и workflows

Точный путь упомянут только в двух workflow invocations и историческом README.
Во всём checked-out repository нет ссылки на исходный SHA-256 test file
`28a70d145c66f4d0832644944ecd1cd1df3aef428255b88187886350caf34399`.
`pure_crate.py` фиксирует hashes controller, wrapper и expected JSON, но не
этого test file. Оба workflow уже включают `diff-crate/**` в path filters.
Их triggers ограничены точными ветками `ci/desktop-diff-crate-20261027` и
`ci/desktop-tabs-crate-20261027`; обычный новый batch/main их не запускает.

Поэтому для этого test-only edit не найден freeze/HOLD coupling, требующий
перезаписи старых receipts. Можно применить edit к active delivery source
в общем reviewed пакете. Старый README описывает исторический AST-only run
и прежний setUp; достаточно коротко отметить новую ревизию в batch report,
не переписывая его прошлую аттестацию как результат нового запуска.

## Сохранённые инварианты и lanes

| Corpus | Почему не удаляется |
| --- | --- |
| Diff 14 controls | Complete/fresh transcript; foreign source/package/version/target; missing/duplicate test/dependency/executable; ignored/filtered/failed outcome; build finish; execution/count binding; JSON и artifact limit. Все сохранены. |
| Tabs 12 controls | Другой 38-name nested corpus, serde_json closure, component manifest/path configuration, два ordered patch stages, replay исходной diff configuration. Похожие ошибки parser не делают эти inputs и coverage одинаковыми. |
| Skills #165/#166 | Shared-owner candidate уже опубликован; standalone current package/private entrypoint contract остаётся нерешённым. Два разных Core pins не являются лишними lanes. Повторного evidence PR или active adoption нет. |
| Envelope #165/#166 | Четыре local policies/controllers и 35 controls на копию включают process/security boundaries и frozen-source coupling. Вне этого slice; не ослаблялись и не запускались. |

Ни один CI lane или отдельный test invariant не удаляется. Одноразовые
observation/oracle drivers предназначены только для локальной проверки,
не предлагаются к добавлению в repository.
