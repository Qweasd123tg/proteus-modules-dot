# Native Pi: один владелец terminal-generation evidence

## Результат

Подготовлен bounded candidate для **известных F1/F2 testing-fidelity из PR85**, поверх PR126. Это не новые findings и не переоценка опубликованных benchmark scores. Исправление отделяет ошибки прошлых попыток от окончательного generation outcome и использует один reducer в adapter/runner и report fallback.

После независимого source review выполнен scoped Python red/green:

- **Baseline Core + PR126: два ожидаемых assertion failures.** Recovered error ошибочно отклоняется; terminal length ошибочно считается clean pipeline.
- **Exact candidate: 9/9 новых synthetic tests прошли.**
- **Отдельный target PR126: 6/6 tests прошли**, с одной уточнённой Pi lifecycle fixture.
- Python **3.12.14**, без installation/dependencies сверх stdlib, native CLI, API/LLM, Rust или benchmark reruns.

Это проверка данных функций на синтетических событиях, **не запуск настоящего Pi**, полный harness/CI gate или доказательство полного accounting. F4 остаётся открытым. Существующие результаты и оценки не переписывались.

## База, dependency и дедуп

- Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules main: `c035142558f0fca43e9772fc0e50ca293abf1531`; Modules и его отдельный Core dependency pin не менялись.
- Delivery main: `9898060357209a43112c65f4cc79e241c1b8d91c`, включает [PR126](https://github.com/Qweasd123tg/proteus-modules-dot/pull/126). Ref values повторно проверены после работы, без изменения.
- **Обязательная source dependency: exact PR126 patch** `c1c30727c0a76fecea815caf22bcb8ed14fdc2e6bd98ab8877027551c760866f`. Новый `pi-terminal-on-pr126.patch` не заявлен как standalone patch к чистому Core. Он использует созданный PR126 `usage_report.py`.
- Pi source contract: tag `v1.5.2` разрешён в commit `b4afdddf44e059c67ccf5097e5317d913521b470`. Реальный installed native binary в этом проходе не проверялся и не запускался.

`SOURCES.json`/`READ-VERIFICATION.json`: 13 exact Git blobs (7 Core и 6 pinned Pi). Сохранены полные файлы для identity, но review ограничен accounting, lifecycle и import/target dependencies. Security, authority, credential handling и прочие flagged paths не исследовались и не менялись.

Исторический report PR85 сохранён в `PRIOR-F1-F2.md`. Его прежние воспроизведения не подменяют новые controls: нынешние два red cases исполнены отдельно на зафиксированной базе.

## Почему старые признаки недостаточны

[Adapter Pi metrics](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/examples/performance/coding-harness/adapters.py#L257-L277) сохраняет все assistant error/aborted в `errors`. [Runner](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/examples/performance/coding-harness/runner.py#L91-L112) требует `not errors`, тогда как final length туда не попадает. `settled` ранее означал наличие любого `agent_end`.

Но [pinned AgentSession](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/core/agent-session.ts#L1967-L1992) после `agent_end` может продолжить retry, compaction и новый low-level run. `willRetry` описывает лишь retryable-error policy и не исключает другие continuations. `agent_settled` из `finally` также не означает успех: он может прийти после exception, а preparation failure до этого `try` вообще не обязан его испустить.

[JSON print mode](https://github.com/earendil-works/pi/blob/b4afdddf44e059c67ccf5097e5317d913521b470/packages/coding-agent/src/modes/print-mode.ts) экспортирует session events, но не применяет text-mode проверку final error/aborted/length exit code. Поэтому exit 0, любой `agent_end` и отсутствие исторической ошибки не дают нужного evaluator outcome.

## Минимальный общий инвариант

Новый `pi_terminal.py` (48 строк, две функции) владеет только этим решением:

1. `agent_start` открывает low-level activity и сбрасывает предыдущий terminal candidate.
2. Новая user/assistant message activity и JSON `message_update` также сбрасывают его. Завершение предыдущей попытки нельзя унаследовать после начавшегося continuation.
3. Последний assistant из `agent_end.messages` считается завершённым кандидатом только после наблюдавшегося start, с явным `willRetry=false` и list-valued messages.
4. Только `agent_settled` фиксирует этот кандидат и literal `aborted`; сам `agent_end` оставляет run pending.
5. Clean predicate требует positive exact-int `expected_turns`, точное число settlements, отсутствие pending tail, для каждого final `stop_reason=stop` и `aborted is False`.

Unknown/missing reasons и `toolUse`/`deferred` не становятся clean success этого evaluator. Это **не универсальное объявление таких outcomes ошибками Pi**. Контракт выбран для текущего coding harness, а не произвольных extensions; обычное toolUse→toolResult→stop внутри одного run отдельно покрыто synthetic control.

Результат остаётся структурированным: `pi_outcome.settlements`, `pending`, `observed_stop_reasons`. Это позволяет отличить final length/error/aborted от отсутствующего terminal evidence. Predicate не является универсальным валидатором произвольного malformed JSON; вне проверенных shapes существующие loaders/consumers могут отказать exception.

## Интеграция и сохранённые свойства

- Adapter не меняет usage rows, sum formulas, model/tool counters, model/provider/reasoning extraction. Старые error/aborted diagnostics сохранены. К terminal length добавляется diagnostic через уже существующий `length limit` taxonomy path; intermediate recovered length хранится в observed stops, но не получает новый terminal-length diagnostic.
- Pi `settled` теперь означает наблюдавшиеся session settlements без pending tail, не просто `agent_end`. Это lifecycle presence, не success: final length может быть settled и одновременно nonclean.
- Runner меняет только Pi completion predicate. Exit code, timeout, model/provider/reasoning verification, canonical error и continuity guards остаются. Codex/OpenCode/Proteus completion policies не переписаны.
- Report Pi fallback читает stdout через тот же reducer вместо отдельного OR всех исторических ошибок. PR126 уже обеспечивает одного владельца report policy для short/long.
- Сохранён `pipeline_ok=true && !timed_out` fast path. **Старые result.json не regrade:** если в них записан ошибочный success, этот patch не исправляет его ретроактивно.
- Старые **неуспешные** artifacts без полноценной start/end/settled boundary теперь дают unknown в fallback. Это явная совместимость с новым доказательным критерием, а не обещание поддержать старые неполные traces.

Главная польза — единое определение final generation вместо несовместимых diagnostic-history/agent_end признаков. Production LOC: adapters `308→314`, runner `271→273`, usage_report `82→77`, новый helper `48`; всего **+51**, не LOC/speed/RSS optimization. Reducer добавляет линейный проход по events в adapter и сохраняет stop/settlement lists; runtime performance/memory не измерялись.

## Точный смысл usage и оставшиеся пределы

Clean final generation не тождественна успешному postprocessing или полноте billing. Например, threshold compaction после final stop может fail без нового agent_start; subsequent settled(false) сохраняет completed generation evidence, тогда как runner всё равно отвергает nonzero exit. Candidate не вводит произвольное требование успеха всех housekeeping events и не сертифицирует auxiliary model accounting.

F4 missing-whole-usage-row, отсутствие отдельных token categories, неизвестные observations и другие accounting gaps не исправлены. Report `usage_complete` остаётся выбранной lifecycle policy; terminal length может оставить полные reported numbers как evidence, но policy не маркирует их clean full totals. Не следует из этого делать вывод, что все числа при таком length фактически неполны.

Generic failure taxonomy по тексту diagnostics не переработана. Например, исторический error message, сам содержащий `length limit`, по-прежнему может получить эту classification независимо от recovery. Новая terminal-length диагностика не заявлена как универсальное решение всех taxonomy cases.

Не доказана поддержка иных native Pi версий, extensions/terminate hints, всех malformed событий или пропавших частей stdout. Нет полного cross-arm recovery parity proof: synthetic Proteus/Codex controls проверяют прежнюю локальную gate policy, а не живые эквивалентные executions.

## Фактическая проверка

`RUN-TARGETS.py` создал две отдельные copies из `before`:
- Baseline содержит Core + exact PR126 production, добавлен **только новый test module**, не implementation.
- Candidate получен strict `git apply --check --whitespace=error` и `git apply`; его bytes совпали с final reviewed `after`.

В обоих процессах использован доступный interpreter с `-B -E -S`, явно заданными PATH/locale и private HOME/TMPDIR, без наследования credentials. Запуск находится в текущем platform sandbox; отдельная OS/network namespace не заявляется и не настраивалась. Наличие/отсутствие packet traffic не измерялось; no-API claim основан на выбранных inspected call paths, а не network capture.

Запуски:

```sh
python3 -B -E -S examples/performance/coding-harness/pi_terminal_test.py \
  PiTerminalChecks.test_recovered_error_is_not_terminal_failure \
  PiTerminalChecks.test_terminal_length_is_not_clean_success -v
# baseline: exit 1, FAILED (failures=2), именно pipeline assertions

python3 -B -E -S examples/performance/coding-harness/pi_terminal_test.py -v
# candidate: exit 0, Ran 9 tests, OK

python3 -B -E -S examples/performance/coding-harness/usage_report_test.py -v
# candidate: exit 0, Ran 6 tests, OK
```

Новые controls: recovered error, final length, recovered length, ordinary tool turn, exact settlement count, missing/invalidated evidence, retained gates/postprocessing distinction, other-arm gates и historical success fast path. Все создают собственные synthetic artifacts. Один continuity subcase одновременно меняет expected count; он не изолирует отдельно continuity guard, неизменность которого также проверена source review.

`runtime/INPUTS-BEFORE.json` и `INPUTS-AFTER.json` одинаковы для исходных sources, before/after и обеих executable copies. Private home/tmp после каждого run пусты. Изменений окружающих source files или исторических benchmark datasets не делалось. Tests не запускали native tools, external graders, harness runner/main, provider/model calls или package manager. Установка не понадобилась, полный suite не выполнялся. Время из unittest logs не является benchmark.

## Evidence

- Patch `pi-terminal-on-pr126.patch` SHA256: `b2b457e7dd2cfb17e1489ef97728080c09b306d9dedd0456f5c2b65b8114a2ee`.
- `CONTRACT-REVIEW.md`: независимый разбор выбранной boundary до patch.
- `SOURCE-REVIEW.md`: independent exact patch/test review до runtime; его NOT RUN относится к той стадии.
- `runtime/PREPARATION.json`, `RUNS.json`, `RESULT.json`, logs и manifests: фактические red/green evidence.
- `RUNTIME-REVIEW.md`: независимая проверка результатов, без повторного исполнения tests.

Ничего не опубликовано мной; upstream production не изменён. Для публикации подходит candidate package с точной PR126 dependency и указанным scoped evidence, не заявление «benchmark полностью исправлен».
