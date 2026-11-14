# Role timeout оставляет процессы субагента работающими после `timed_out`

2026-11-13. Новая подтверждённая lifecycle-находка; предлагаемый приоритет **P1**. Не относится к MCP reload, reset pool или уже известной broker cancel race. Production-код не менялся, ничего не опубликовано.

## Что происходит

Root запускает process peer, тот запускает долгую локальную команду. При `agent_control.roles[].timeout_ms` Core завершает **только процесс peer**, возвращает `status=timed_out`, но работа команды продолжается без живого peer. Проверено не только на синтетическом workflow, но и через штатный **`proteus-shell-tool-module` → `exec_command`**.

В финальном shell-прогоне:

- `spawn_agent` успешно запускает `/root/peer`;
- peer вызывает обычный `exec_command`, `tty=false`, `yield_time_ms=10000`;
- на role deadline 2500 мс root получает через `wait_agent`: `status=timed_out`;
- child Core и его workflow уже отсутствуют;
- shell PID 185 остаётся живым, его PPID уже `1`; Python marker PID 191 остаётся дочерним процессом shell;
- **через 1,653 секунды после успешного ответа root** marker создаёт файл;
- в момент проверки, ещё через несколько секунд, оба процесса живы и спят;
- собственные процессы затем явно остановлены диагностикой, cleanup сохранён.

`wait_agent.output.timed_out=false` здесь означает, что само ожидание закончено результатом; статус агента внутри `agents[]` равен `timed_out`. Это не ошибка интерпретации wrapper timeout.

Никаких пользовательских файлов, daemonization, `setsid`, специально убегающего процесса или сетевых моделей нет. Fixture-команда только пишет свой JSON marker в собственном временном workspace и спит; имеет 15-секундный alarm как дополнительный предел. Synthetic allow-all policy разрешает только предусмотренный диагностикой запуск; `with_escalated_permissions=true` находится в локальном tool call, системные security/sandbox settings не менялись.

## Матрица и контроли

Два независимых полных прогона, по четыре случая: **8 проверенных случаев**.

| Сценарий | Ответ о peer | После ответа | Marker |
|---|---|---|---|
| Custom workflow запускает обычный helper; role timeout | `timed_out` | helper жив, PPID=1 | создан позже ответа |
| Тот же workflow/helper; timeout самого component export | `errored`, module run timed out | helper остановлен | отсутствует |
| Штатный shell `exec_command`; role timeout | `timed_out` | shell и helper живы, shell PPID=1 | создан позже ответа |
| Тот же shell command; `interrupt_agent` во время исполнения | `cancelled` | helper и shell остановлены | отсутствует |

Во всех случаях fixture достоверно дошла до `helper-started`; отсутствие marker в controls не объясняется отсутствующим запуском. В user-cancel control сам peer остаётся в idle pool, что нормально; прекращена именно его текущая команда.

`verify.py` подтверждает воспроизведение **дефекта**, а не корректность продукта. Отдельный `expected_invariant.py` проверяет желаемое прекращение команды и даёт **2 FAIL + 2 PASS**, exit code 1. Полного workspace gate, live LLM, GUI или Windows-проверки не было.

## Причинная цепочка

Core HEAD `89997df995df7c39b713e16aba216ecb19c8f497`; Modules HEAD `3270dc0f894eaf4d0360306052b806099b8f5351`. Оба сверены с remote HEAD в этом проходе. Проверенные source-файлы точно совпадают с HEAD (`source-hashes.json`).

1. [process/mod.rs:320–342](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/mod.rs#L320-L342): внешний `timeout_at` прерывает `drive_turn`, превращает deadline в error, вызывает `child.kill()`, затем отдаёт `TurnEnd::Interrupted(TimedOut)`. Нормальная cancel/grace цепочка не вызывается.
2. [process/child.rs:42–58](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/child.rs#L42-L58) и [219–220](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/child.rs#L219-L220): peer запускается с `kill_on_drop(true)`, а принудительное завершение есть только `tokio::process::Child::kill()` прямого PID.
3. [ProcessTransport:258–262](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-process-host/src/transport.rs#L258-L262): каждый module component имеет свою отдельную process group, которой управляет именно живой child Core. Убийство Core не выполняет `Drop` его transport и их group cleanup.
4. [shell process.rs:279–286](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/shell-tool/src/unified_exec/process.rs#L279-L286): pipe command также запускается в собственной группе. Простое добавление process group вокруг peer недостаточно: дочерние components и shell уже имеют отдельные группы.
5. Обычная отмена отличается: [turn.rs:480–506](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/turn.rs#L480-L506) отправляет `StdioRequest::Cancel`, даёт peer обработать отмену и ожидает terminal response. Именно этот control в стенде корректно остановил native shell job.

Результат не следует списывать на недобросовестный custom module: второй repro проходит через поставляемый shell tool. Не утверждаем, что любой background process обязан завершаться после обычного успешного turn: проверяется **ещё исполняющийся вызов** при deadline роли, до возврата его `exec_command`.

## Последствия и направление исправления

Ограничение времени агента сейчас не ограничивает время его запущенной работы: команды способны продолжать менять workspace после того, как root считает peer завершённым по timeout. В стенде это доказано только harmless marker; повреждения реальных данных не моделировались и не заявляются.

Нужно различить deadline во время setup/незавершённой записи и во время уже корректно отправленного Send. Для активного turn сначала необходим bounded cancel/grace путь с подтверждённым cleanup. Для принудительного fallback нужен реальный ownership всего дерева/ресурсов peer, учитывающий отдельные process groups components и terminal commands. Без этого замена `child.kill` на `killpg(peer)` не закрывает воспроизведённый shell-case. Это направление, не готовый проверенный production patch.

Regression должен запускать peer с долгим harmless `exec_command`, дождаться начала команды, превысить role deadline и проверять отсутствие поздних marker-записей и оставшихся owned процессов. Рядом оставить user-cancel control.

## Артефакты и воспроизведение

- `repro.py`, `workflow.py`, `helper.py`: тестовый стенд.
- `run-3.log`, `run-4.log`: финальные полные матрицы.
- `run-1794583038262812071/`, `run-1794583099794922761/`: configs, stdio outputs, локальные canonical sessions, markers, результаты, cleanup.
- `verification.log`, `expected-invariant.log`, `source-hashes.json`.
- `run-1.log`: предварительный fixture setup без `parallel_safe`, агент не запускался.
- `run-2.log`: первый exploratory proof; root fixture тогда не возвращала persistent message. Это исправлено до двух финальных полных матриц; эти старые логи не используются как основной gate.

```bash
python3 repro.py --core /path/to/Proteus-core --binary /path/to/proteus --shell /path/to/proteus-shell-tool-module
python3 verify.py run-.../results.json
python3 expected_invariant.py run-.../results.json
```

Повтор использует Linux `/proc`; все command/workspace/profile paths принадлежат стенду. Готовые чистые binary были собраны ранее и повторно не собирались:

- Core SHA-256 `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`.
- Shell module SHA-256 `810acf3e4f33ebfc7a530e9db16687173927f3ca770d3c641d5b82a985464dd0`.
- Shell build использует штатный Modules `Cargo.lock` с Core dependency `b5fac842...`, как и ранее проверенная clean сборка. Это не утверждение, что module SDK отдельно пересобран с текущим Core HEAD.

Публикаций, PR или production-патчей в этом проходе нет.
