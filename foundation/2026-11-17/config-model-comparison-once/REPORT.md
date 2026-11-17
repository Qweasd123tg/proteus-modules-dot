# Одно сравнение model source на сохранение

Проверенный локальный source-кандидат, не применение к upstream или CI.

## Результат

В `app_server/config_builder/persistence.rs` каждый TOML/JSON writer сначала
вычислял `model_source_changed(config, baseline)` для выбора обработки inline
роли, затем повторял то же вычисление в private helper. Между вызовами меняется
только локальный документ; сравниваемые `config` и `baseline` неизменны, `await`
нет. Теперь уже вычисленная пара передаётся helper-у.

При существующем baseline это убирает две повторные JSON-сериализации каталогов
providers и одно повторное сравнение на сохранение. Первый вызов и его порядок
ошибок остаются прежними. Guards, наследование, файловые операции, locks,
разрешение target, API и тесты не изменены. Нового framework или cache нет.
Измеренного ускорения не заявлено. Diff: один файл, **+8/−8**, не экономия LOC.

База: Core `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`, main перепроверен
через GitHub в этом проходе. Локальный commit:
`6f94d62d6e987e7c6e32d264ddde9fe2429bb006`.

## Проверка

- Native Rust 1.95.0, Cargo `--offline --locked -p proteus-core --lib`:
  **те же 17 существующих persistence/load cases проходят до и после**.
  Это 34 успешных исполнения, не 34 уникальных теста.
- Покрыты named models (4), inline roles (5), instruction bootstrap (3),
  provider inheritance (3), directory precedence и unmanaged JSON (2).
  TOML/JSON, отсутствующий baseline, изменённый выбор/каталог, неизменённые
  источники, сохранение siblings и общая идентичность write lock проверяются
  существующими сценариями. Test names записаны в `VERIFICATION.json`.
- **Начальная baseline-команда целиком не зелёная:** дополнительный 18-й
  hook-order case остановился на отсутствии `PROTEUS_TEST_REFERENCE_MODULE`
  в fixture setup, до persistence. Process не запускался. Этот несвязанный
  case не включён в candidate-команду; его failure не скрыт и не исправлен
  подстановкой фиктивного executable.
- Прямой Cargo выбран потому, что обычный Core runner для любого `--lib`
  готовит все module binaries. Здесь выполнен только указанный чистый
  config scope, без `AgentAppServer::launch` и process fixtures.
- Targeted rustfmt, `git diff --check`, strict whitespace forward/reverse
  apply и точное восстановление исходных bytes: PASS.
- Независимый review: ACCEPT; reviewer сверил совпадение 17 успешных имён
  baseline/candidate и неизменность точного patch SHA.

Full workspace, process/security/isolation checks, hosted CI, portable и
benchmarks не запускались. Два прежних `dead_code` warning в profile polling
присутствуют в обоих native logs. Совместимость с отдельным composed commit
`b2c285f` не квалифицирована: из-за добавленного `inherited_choice` аргумента
патчу нужен небольшой rebase, а не слепое применение поверх него.

## Что не удалено и почему

- Второе разрешение config-builder target после `await` выглядит повтором,
  но helper читает `is_dir`/`canonicalize`: внешний редактор может изменить
  filesystem вне нашего write lock. Оно не объявлено лишним и не изменено.
- В fresh Core/Modules manual workflows нет доказанного повторного full gate.
  Core runner-selection tests проверяют выбор feature/fixtures, а не факт
  существования тестов. Standalone SDK smoke проверяет отдельный потребитель.
- PR165 имел **0 безопасных безусловных удалений тестов**. PR166 уже предлагает
  shared owner четырёх копий skills scripts/tests, сохраняя оба Core-pin lanes,
  но standalone packaging остаётся открытой границей. Повторные definitions
  не означают ненужные executions разных implementations/pins.
- Envelope consolidation из PR165/166 затрагивает исключённые из этого
  прохода process/filesystem controls. Здесь только прочитаны старые отчёты;
  эти области, HOLD и active validation freezes не менялись.

Новых тестов, тестов-счётчиков вызовов, CI wrappers и массового удаления
похожих сценариев нет.
