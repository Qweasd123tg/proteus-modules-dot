# Benchmark reproducibility: stale OpenCode continuation snapshot

Проверено 2026-11-13 на Proteus-core `89997df995df7c39b713e16aba216ecb19c8f497`. Перед/после проверки remote main имеет тот же SHA; рабочая копия чистая. Production-код не менялся, публикаций и обращений к моделям не было.

## Подтверждённый дефект P2: прерванный follow-up теряет уже сохранённые в БД шаги

Граница: `examples/performance/coding-harness/runner.py:249–255`, жизненный цикл `run_turns` на строках 139–169 и удаление временной БД на строках 77–88. `open_code_native.py:118–142` сохраняет один cumulative `runtime/native/usage.json`, который повторно используется при продолжении той же сессии.

После первого успешного OpenCode turn остаётся `usage.json` с его завершённым snapshot. Если второй или третий turn завершил часть запросов/действий, но затем timeout убил wrapper до `save_usage()`, runner извлекает живую БД **только при отсутствии** `usage.json`. Уже существующий файл блокирует fallback. В метрики попадает предыдущий turn, после чего `remove_auth()` удаляет БД с более свежими данными. Таким образом теряется не только неизвестный usage активного запроса, но и уже committed assistant/tool evidence текущего follow-up.

### Воспроизведение

`python3 -B repro_stale_snapshot.py` использует настоящие `runner.main`, `run_turns`, `execute`, bwrap и `open_code_native.save_usage`. Только `adapters.prepare` заменён на staging локального synthetic worker без модели/ключей. Worker создаёт минимальную SQLite схему, соответствующую запросам extractor:

1. Первый turn записывает 1 user/1 assistant, 10 input tokens, успешно сохраняет snapshot через настоящий `save_usage(after_logout=True)`, завершается.
2. Второй turn добавляет ещё user, завершённый assistant с одним tool, повышает cumulative input до 30, выставляет `idle_outcome=running` и зависает до реального timeout runner.
3. Независимое чтение той же БД до ожидания сохраняет контрольный snapshot. Это только диагностическая копия, runner его не использует.

Получено дважды:

| Метрика | Сохранено runner | Уже было в БД |
|---|---:|---:|
| User turns | 1 | 2 |
| Assistant messages | 1 | 2 |
| Input tokens | 10 | 30 |
| Tool calls | 0 | 1 |
| `partial` | false | true |
| `settled` | true | false |

`turn_returncodes=[0,-15]`, `timed_out=true`, `pipeline_ok=false`, БД после завершения удалена.

Контроль: после того же timeout удалить только старый `usage.json` перед финализацией runner. Имеющийся production fallback немедленно извлекает 2 user/2 assistant/30 input/1 tool, `partial=true`, `settled=false` из той же схемы. Это подтверждает, что данные доступны и extractor их поддерживает; виноват existence gate, а не отсутствие usage у модели.

### Влияние и ограничения

- Влияет на прерванные multi-turn native OpenCode сценарии, в том числе формат `go-review`, после хотя бы одного удачного turn.
- Общий результат **не становится PASS**: timeout корректно оставляет `pipeline_ok=false`.
- Это отдельный дефект свежести per-turn snapshot. Он отличается от ранее найденных missing-usage summation / lower-bound labeling ошибок.
- Не доказывает, что опубликованные таблицы содержат эту ошибку. В tracked `2026-11-11-deepseek-long.json` native OpenCode/go-review attempts 1 и 2 успешно завершили все 3 turns (`timed_out=false`, continuity=true), то есть воспроизведённое условие для них не наблюдается. Живые исходные БД исторических прогонов недоступны.
- Synthetic worker не является настоящим OpenCode binary. Проверены реальные Python runner, ОС timeout/process lifecycle, SQLite extraction и cleanup, но не частота такого исхода у конкретной версии upstream OpenCode.
- Модели, сеть провайдеров, credentials, production sessions не использовались. bwrap открывал только одноразовые рабочие каталоги и readonly системные файлы.

### Направление исправления

Привязывать snapshot к конкретному завершённому turn, а при прерывании/неуспехе очередного turn извлекать доступную БД независимо от наличия старого snapshot, до credential cleanup. При ошибке extraction старую копию помечать как stale, а не выдавать за актуальное состояние. Не убирать удаление credential DB.

Регрессия должна включать: успешный turn → committed model/tool шаг второго turn → timeout; ожидать свежие partial метрики и сохранение `pipeline_ok=false`.

## Остальные проверки

- 14 existing coding-harness `runner_selfcheck`/`adapters_test`: PASS.
- 6 existing CodeMode fixtures/measurement tests: PASS.
- Просмотрены runner/matrix/report/long_report, long corpus preparation, CodeMode run/measure, multi-agent run/proc, history-scale fixture/run, build-iteration и session-db. Других новых подтверждённых дефектов в этом проходе нет.
- Python 3.12.14.

## Evidence

- `repro_stale_snapshot.py`: автономный повтор, создаёт новый одноразовый каталог при каждом запуске.
- `stale-snapshot-result.json`, `repro.log`: сравнение реального поведения с контролем.
- `harness-existing-tests.log`: 14 PASS.
- `code-mode-existing-tests.log`: 6 PASS.
- `source-sha256.txt`: hashes проверенных исходников и regression.
