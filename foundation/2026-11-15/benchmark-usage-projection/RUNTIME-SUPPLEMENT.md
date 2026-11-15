> Sanitized publication copy. Raw logs, launcher, execution environment paths and private artifacts are deliberately not published. Named original evidence and hashes below refer to retained review inputs, not bundled files.

# F3 usage projection: целевая Python-проверка

## Итог

После отдельного разрешения на проектные прогоны выполнен **один запуск ровно шести synthetic unit tests** из `usage_report_test.py`. **Python 3.12.14; exit 0; `Ran 6 tests ... OK`.** Установка зависимостей не понадобилась: этот target и импортированные им `report`, `long_report`, `usage_report` используют Python standard library.

Это дополнение к предшествующей source-only стадии, а не изменение её истории. Сохранённые `REPORT.md`, `USAGE-INDEPENDENT-REVIEW.md` и `PATCH-VERIFICATION.json` в соседнем исходном artifact описывают состояние **до** разрешённого прогона. Их прежнее `NOT RUN` теперь дополнено фактическим результатом только для этих шести Python tests. Остальные кандидаты, Rust gates и другие project targets этим не проверены.

## Проверенная база и неизменность

- Core: `bcbda4435534a296c707a1daa250813d692f68e1`. GitHub `main` повторно проверен до и после прогона: тот же commit; финальный ответ сохранён в `CORE-REF.json`.
- Patch SHA256: `c1c30727c0a76fecea815caf22bcb8ed14fdc2e6bd98ab8877027551c760866f`.
- Из отдельных проверенных base blobs `report.py`, `long_report.py`, `README.md` создан новый каталог `isolated`. Patch применён без правок через `git apply --whitespace=error` после успешного `--check`.
- Полученные пять файлов побайтово совпадают с ранее independently reviewed `after`. До/после запуска их состав и SHA256 неизменны (`CANDIDATE-BEFORE.json`, `CANDIDATE-AFTER.json`).
- Состав и SHA256 всего исходного artifact `original source artifact` до/после также неизменны (`ORIGINAL-ARTIFACT-BEFORE.json`, `ORIGINAL-ARTIFACT-AFTER.json`).
- Существующие benchmark datasets, результаты/оценки, historical report inputs и окружающие project files не копировались для выполнения и не изменялись. Fixture данные создавались самими tests во временном каталоге; после завершения private TMPDIR и HOME пусты.

`PREPARATION.json` сохраняет Git blob identities и обе Git-команды. `RUN-TARGET.py` сохраняет подготовку, точную команду и проверки manifests. Этот driver отказывается повторно создавать существующую копию, поэтому он не является автоматически повторяемым runner поверх уже использованного каталога.

## Команда и границы исполнения

Из корня отдельной копии, доступным interpreter:

```sh
python3 -B -E -S examples/performance/coding-harness/usage_report_test.py -v
```

Абсолютный путь interpreter, его `sys.version`, command argv, cwd, полный минимальный environment, времена и return code записаны в `RESULT.json`; stdout пуст, полный unittest output находится в `stderr.txt`. `-B` запрещает запись bytecode cache; `-E` игнорирует Python environment overrides; `-S` не загружает site packages/startup hooks. Environment передан явно с private HOME/TMPDIR, PATH и locale, без наследования пользовательских credentials.

Выполнялись только эти local synthetic tests. Не запускались model/provider requests, external API/LLM, native CLI, adapters, harness runner, graders, benchmark reruns, package manager или dependency installation. В доступных test путях нет сетевого вызова. Это вывод из проверенного target/import graph и фактически выбранного запуска, **не утверждение о packet capture или отдельной network-isolation проверке**.

Дополнительный `bwrap --unshare-net` preflight закончился **до запуска project code** с `NETLINK_ROUTE socket: Operation not permitted`. Он не прошёл и не обозначен как успешный sandbox test. Не было escalation, изменения OS settings или установки альтернативного backend. Проверка выполнена в отдельной файловой копии и чистом environment внутри текущего platform sandbox; **новая OS/network namespace не заявляется**. Точная неуспешная preflight-команда сохранена в `ISOLATION-PREFLIGHT.json`.

## Шесть прошедших controls

1. Short/long row evidence для complete и timed-out fixture; source fixture bytes не меняются.
2. Primary complete grader-fail + timed-out primary + successful repeat: pass denominators сохранены, incomplete full totals неизвестны, partial lower bounds суммируются отдельно, repeat не входит в primary totals.
3. Lifecycle-complete run с отсутствующей token category не получает выдуманный full total; partial observation сохраняется.
4. Явный zero и отсутствие observation различаются coverage; `tokens` и `reported_usage` не делят изменяемый dictionary.
5. Существующая Pi/Proteus teardown completion policy не заменена простым `pipeline_ok`.
6. Guard разных prompt/repository identities продолжает отказывать.

Полные test method names присутствуют в `stderr.txt`. Время `0.009s` в unittest log — длительность этих synthetic tests, **не performance benchmark** и не оценка скорости/стоимости агента.

## Что результат не доказывает

- Это focused unit gate для данного patch, не полный Core/Modules suite и не CI run. Тесты выполнялись на Python 3.12.14, не на всех поддержанных версиях.
- Не выполнялся baseline/red-green запуск этих tests на unpatched коде. Источник дефекта F3 и scope кандидата остаются подтверждёнными прежним source review; текущий прогон показывает прохождение candidate controls, а не отдельное runtime сравнение всей базы.
- Исторические benchmark таблицы не регенерировались. Тезис о неизменных корректных complete integer totals ограничен source equivalence и synthetic controls, не измеренным сравнением всех старых runs.
- F1/F2 (исходная lifecycle policy) и F4 (adapter whole-usage omission) **остаются открытыми**. `usage_complete` по-прежнему не означает полноту каждой token category. Разные caller selections short/long, legacy `known_token_runs` semantics и новые чтения native evidence для incomplete short rows не изменены.
- Canonical-journal dynamic import, OpenCode lifecycle branch, malformed-artifact/I/O failure cases и CLI rendering/build всех длинных отчётов не получают отдельного покрытия этими шестью tests.
- Нет Rust build/test, живой модели, hardware/performance claim, upstream merge или production rollout.

Независимый review фактического результата сохраняется отдельно в `RUNTIME-INDEPENDENT-REVIEW.md`.
