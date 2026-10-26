# Изолированный пакет исправлений чтения истории

Дата: 26 октября 2026. Это **переносимые patches и целевые regression gates**,
а не подключение новых модулей или готовая desktop-поставка.

## Что входит

- **Core** — восстановление отсутствующего/повреждённого производного read-index
  при чтении полного transcript и страниц; строгая проверка revision, сохранение
  canonical journal и bounded recovery. Startup-чтение SQLite перенесено внутрь
  существующего blocking worker. Подробности: [core/README.md](core/README.md).
- **Desktop** — повторная догрузка после отменённого запроса на неизменившемся
  снимке, защита от поздних ответов и параллельных повторов, явный Retry после
  ошибки вместо бесконечных повторов при перерисовке. Подробности:
  [desktop/README.md](desktop/README.md).

## Точные источники

| Пакет | Репозиторий и commit |
| --- | --- |
| Core | `Proteus-harness/Proteus-core@7435f2a6d90e532665ebed4da67526b609158fc8` |
| Desktop | `Proteus-harness/Proteus-desktop@5748ac04f78eaffa1f4ea6102bd349ca61412e8d` |

Происхождение исходных Git blobs и SHA256 patches сохранены рядом с каждым
пакетом. `manifest.json` фиксирует проверяемые пути, порядок применения,
полные имена tests и SHA256 исполняемых входов. Patches предназначены именно
для этих commits; они не применяются автоматически к изменившемуся upstream.
Сохраняются лицензии и авторство соответствующих upstream-файлов; это не
перелицензирование Core, Desktop или Zed.

## Изоляция от модулей

Пакет размещён в `performance/2026-10-26/` на отдельной ветке
`ci/speed-patch-validation-20261026`, основанной на исходном `main`
`206bcb9222d3e8692643cb083f809859a17f1335`.

- PR #21 и его head `a5ec37973a23642c38488c6a425aa0b27765f62b` не меняются.
- Исходники существующих модулей и их workflows не меняются.
- Дополнительный `.github/workflows/speed-patch-validation.yml` действует
  только в этом репозитории и на этой точной экспериментальной ветке.
- Upstream Core/Desktop не получают commits, PR, изменённых CI triggers,
  release или deployment. Слияния и auto-merge нет.

## Проверка

CI на отдельных hosted runners использует официальный Rust `1.95.0`.
`run_validation.py` получает закреплённый source commit, проверяет исходные
Git blobs и package SHA256, применяет только перечисленные patches с
`git apply --check --index`, затем запускает указанные целевые проверки.

Для Core: сначала tests-only patch и **ожидаемый FAIL конкретного regression**,
затем production patch и обязательные **PASS по именам**. Ошибка компиляции,
подготовки или пустой фильтр не считаются доказательством воспроизведения.
Политика baseline Desktop явно описана в его README и manifest.

Evidence содержит bundle commit, source commit/tree, tests-only и patched
деревья, hashes изменённых файлов, фактические commands и exit codes.
Логи ограничены хвостом 64 KiB на command; полные build logs доступны в run.
Время commands включает компиляцию/подготовку и **не является замером ускорения**.

Первичный статус: patches независимо проверены статически; runtime evidence
появляется только после завершения соответствующего CI run. Состояние
`success` не подразумевает полный workspace gate, запуск реального окна,
проверку portable, production release или измеренное ускорение UI.
