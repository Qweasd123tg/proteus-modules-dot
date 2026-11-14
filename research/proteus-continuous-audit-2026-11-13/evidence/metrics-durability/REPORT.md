# Benchmark metrics durability: Ctrl+C and partial native export

Дата: 2026-11-13. Proteus-core `89997df995df7c39b713e16aba216ecb19c8f497`; remote HEAD проверен перед и после прохода, совпадает. Production checkout чистый, исходники не менялись. Публикаций, живых моделей, сетевых вызовов провайдеров и настоящих credentials не было.

## 1. Новый подтверждённый P2: Ctrl+C удаляет единственную БД usage до извлечения метрик

### Граница и причина

- `examples/performance/coding-harness/runner.py:56–74`: `execute()` обрабатывает `TimeoutExpired`, но не `KeyboardInterrupt`.
- `runner.py:242–265`: внешний runner также не перехватывает `KeyboardInterrupt`. Управление перескакивает через extraction/metrics/check_pipeline прямо в `finally: remove_auth(runtime)`.
- `runner.py:77–88`: cleanup удаляет disposable OpenCode DB, `-wal` и `-shm`; комментарий предполагает, что безопасные метрики уже извлечены. Для данного пути это неверно.
- `result.json` пишется **после** finally, поэтому при таком выходе его тоже нет.
- `long_report.py:290–294`: существующий каталог без `result.json` отображается как `state=running`, хотя процесс уже завершён.

Исходники: [runner](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/runner.py#L242-L265), [cleanup](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/runner.py#L77-L88), [classification](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/long_report.py#L290-L294).

### Воспроизведение

`python3 -B repro_interrupt.py`

Запускается настоящий `runner.main`, `run_turns`, `execute`, `sandbox_command` и bwrap. Подменяется только `adapters.prepare`, чтобы вместо модели запустить synthetic worker с минимальной SQLite схемой, соответствующей production extractor.

1. В **первом turn** worker commits 1 user message, 2 assistant messages, 30 input tokens и 1 tool call.
2. Настоящий `open_code_native.save_usage` сохраняет независимую контрольную копию. Harness её не использует; она доказывает доступность данных до остановки.
3. Worker выставляет ready marker и ждёт. `runtime/native/usage.json` ещё никогда не создавался, как при прерывании wrapper до его finally/export.
4. Родитель отправляет SIGINT именно Python runner, то есть выполняет Ctrl+C-equivalent. `execute` запускает agent в отдельной session, поэтому signal interrupt runner не тождественен его штатному timeout/terminate child path.
5. Контрольный запуск использует тот же worker, но дожидается обычного 10-second deadline runner.

| Наблюдение | SIGINT | Штатный deadline |
|---|---|---|
| Exit runner | -2 (SIGINT / KeyboardInterrupt) | 1 (неуспешный benchmark) |
| `result.json` | отсутствует | сохранён |
| `runtime/native/usage.json` | отсутствует | сохранён |
| input tokens | неизвестно, сохранено не было | 30 |
| tool calls | неизвестно, сохранено не было | 1 |
| disposable DB удалена | да | да |
| `long_report.read_trial().state` | `running` | `awaiting_grader` |

SIGINT/timeout пара воспроизведена повторно с тем же результатом. Traceback показывает `KeyboardInterrupt` в `runner.execute → subprocess.wait`, не ошибку synthetic worker. Grader намеренно не запускался, поэтому контрольный state `awaiting_grader` корректен.

### Влияние и ограничения

- Потеря касается **уже committed** native usage и tool evidence, а не только неизвестных токенов ещё активного ответа. В production после cleanup нет доступной безопасной копии этих метрик; диагностическая независимая копия существует лишь в этом repro.
- Отсутствие terminal receipt относится к любому agent при этом пути; невосстановимая потеря удалённой SQLite DB непосредственно доказана для OpenCode.
- Это отдельная причина от прежнего stale-follow-up snapshot: здесь первый turn и экспорт ещё ни разу не сохранялся.
- Общий PASS не возникает. Ошибка делает законченный прерванный прогон похожим на ещё выполняющийся и исключает доступные метрики из последующего отчёта.
- Проверен SIGINT, не SIGKILL, внезапное отключение машины или конкретный upstream OpenCode binary.
- Не утверждается, что остановленные исторические прогоны пользовались этим способом. Tracked исторические таблицы этим тестом не опровергнуты.
- Инвентаризация host child PID недоступна в subprocess namespace этого execution environment. Отдельного вывода об утечке процессов этот тест не делает.

### Направление исправления

Сделать мягкую отмену отдельным terminal path: прекратить и дождаться принадлежащего runner процесса/дерева, извлечь доступные safe partial metrics **до** credential DB cleanup, затем сохранить terminal receipt с причиной `interrupted`, а не оставлять отсутствие `result.json`. Cleanup credentials сохраняется обязательным. Состояние interrupted не должно позволять продолжение следующего turn или PASS. Итоговую запись желательно делать атомарно и гарантировать её также при обработанном interrupt. Не обещать восстановление после SIGKILL этим исправлением.

## 2. Дополнительный regression прежнего existence-gate: обрезанный export первого turn

Это **расширение уже известного finding**, а не второй независимый новый баг.

`python3 -B repro_partial_export.py` ограничивает **только synthetic worker** через `RLIMIT_FSIZE=256`, после успешного commit SQLite и контрольного export. Игнорирование `SIGXFSZ` позволяет настоящему `Path.write_text` получить короткую запись + `OSError(EFBIG)`. Не заполняется диск, окружение runner-родителя не меняется.

`open_code_native.py:137–142` пишет `usage.json` неатомарно. После ошибки остаётся 256 bytes invalid JSON. `runner.py:249` видит существующий файл и не перечитывает доступную БД. `adapters.metrics` возвращает JSON decode error; DB затем удаляется. В результате нет ни 30 input tokens, ни 1 tool call.

Контроль: удалить только обрезанный `usage.json` после завершения worker. Существующий production fallback сразу сохраняет корректные 30 tokens/1 tool из той же DB; итог всё равно `pipeline_ok=false` из-за export/worker error.

Значит, для исправления прежнего stale-snapshot недостаточно полагаться на existence: нужны freshness/validity и безопасный повторный export при неуспешном turn. Atomic replace устраняет неполный новый JSON, но сам по себе не устраняет прошлый корректный устаревший snapshot. Политика credential cleanup не должна ослабляться.

## Остальные проверки

- `python3 -B -m unittest discover -s examples/performance/coding-harness -p '*test.py' -v`: 5 PASS.
- `python3 -B -m unittest discover -s examples/performance/coding-harness -p 'runner_selfcheck.py' -v`: 9 PASS.
- Просмотрены main/execute/run_turns, adapters metrics, native usage extraction, report/long_report completion и classification, CodeMode run/measurement, sampler aggregation, session-db wrappers, replay/limit controls, session usage projection.
- Гипотеза «history-scale выдаёт missing smaps за нулевую память» отвергнута: `Metrics.sample()` явно завершает subject case ошибкой на `memory_incomplete_pids`. Общий full-tree read-only summary не использован как доказательство дефекта production subject measurements.
- Никаких новых утверждений об ошибочности исторических benchmark цифр не делается. Полного Rust/workspace gate не запускали: production код не менялся, проверки Python harness целевые.

## Артефакты

- `repro_interrupt.py`, `interrupt-result.json`, `interrupt.log`; временные `interrupt-runs-*/` содержат worker/driver, traceback, реальные output каталоги.
- `repro_partial_export.py`, `partial-export-result.json`, `partial-export.log`; `export-runs-*/` содержит обрезанный JSON и контрольные snapshots.
- `adapters-tests.log`, `runner-tests.log`, `source-sha256.txt`.
