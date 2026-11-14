# P2: task скрывает timeout дочернего агента от родительской модели

Дата: 2026-11-13. Remote HEAD повторно проверен: Core `89997df995df7c39b713e16aba216ecb19c8f497`, Modules `3270dc0f894eaf4d0360306052b806099b8f5351`. Production-исходники не менялись; commit/push/PR нет.

## Подтверждённый результат

При истечении `agent_control.roles[].timeout_ms` backend правильно фиксирует `timed_out`, но `task` возвращает `ToolResult::ok` и сохраняет статус только в metadata. Native model adapter эту metadata модели не отправляет. Поэтому модель получает успешный пустой результат или незавершённый текст без сообщения о таймауте.

Реальная проверенная цепочка:

`root Core server stdio → coding.codex_loop → штатный TaskTool → настоящий child Core process → role timeout → TaskTool → native Anthropic adapter → HTTP capture на 127.0.0.1`.

| Сценарий | Событие backend | Фактический tool_result для модели |
|---|---|---|
| Положительный контроль: child завершён | `completed` | Полный synthetic summary и task_id, `is_error=false` |
| Child workflow задержан на 4000 ms, role limit 1500 ms | `timed_out` | `content="(no output)", is_error=false` |
| Повтор предыдущего в новой session | `timed_out` | То же |
| Child использует штатный delayed fake model, 400 ms на слово | `timed_out`, 1 iteration | `content="Fake final answer. ", is_error=false` |
| Контроль: `collaboration` → `spawn_agent` → `wait_agent` | `timed_out` | JSON с `agents[0].status="timed_out"` виден модели |

В partial-stream case это не завершённый ответ: child journal содержит `model_request_recorded`, но не содержит `model_response_recorded` или `turn_settled`. Родитель получает только первые слова и не узнаёт причину обрыва. Root workflow при этом успешно продолжает работу и делает следующий native HTTP-запрос: проблема не ограничена display metadata.

Для timeout без текста сохранено:

```json
{"ok":true,"output":"","error":null,"metadata":{"status":"timed_out","resumable":false}}
```

Но следующий реальный запрос провайдеру содержит:

```json
{"type":"tool_result","content":"(no output)","is_error":false}
```

Это одна root-cause группа, не отдельные баги empty/partial. Не повтор worktree cleanup, IDs, ReloadTools или прежнего output-budget дефекта.

## Причинная цепочка

1. [Process role timeout, Core process/mod.rs:320–342](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/mod.rs#L320-L342) корректно превращает истечение deadline в `TurnEnd::Interrupted(TimedOut)` и останавливает child.
2. [Process result, строки 483–524](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/mod.rs#L483-L524) сохраняет partial text отдельно от lifecycle status.
3. [TaskTool result_to_tool_result, task.rs:158–182](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task.rs#L158-L182) использует summary как output, кладёт status в metadata и **безусловно** создаёт `ToolResult::ok`.
4. [Contracts text_or_status, tool.rs:151–185](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/domain/tool.rs#L151-L185) не включает metadata: возвращает output или `(no output)`.
5. [Native Anthropic, request.rs:319–325](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/request.rs#L319-L325) отправляет именно этот текст и `is_error = !result.ok`. HTTP-путь подтверждён. [OpenAI request.rs:401–416](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/openai/request.rs#L401-L416) использует тот же text_or_status и также не передаёт status; этот второй provider проверен только чтением кода.

Контроль с collaboration важен: его JSON summary содержит lifecycle status в обычном output, поэтому модель видит timeout. Backend не теряет статус; дефект находится в task facade / model-visible проекции.

## Пользовательское последствие и исправление

Родительский агент не может надёжно отличить успешную пустую задачу от истечения лимита, а partial summary выглядит как обычный результат делегирования. Модель лишена информации для решения повторить, сузить или продолжить работу. Синтетический provider не оценивает качество ответа, поэтому не заявляем, что реальная LLM обязательно сделает неверный вывод.

Нужно сделать **любой non-completed lifecycle status явной частью model-visible результата** и пометить partial summary незавершённым. Можно выбрать контракт с error result или структурированным текстовым envelope; одного изменения metadata недостаточно. Не следует подменять completed status или терять полезный partial text. Regression должен проверять фактический provider request, а не только внутреннюю metadata. Cancelled-путь использует тот же formatter, но его end-to-end поведение отдельно не воспроизводилось.

## Артефакты и границы

- `run.py`: пять независимых process-chain сценариев с изолированными HOME/workspace/config/session. Свежий root process на каждый case, никакого Git worktree.
- `child_workflow.py`: безопасная model-free фикстура задержки; partial case вместо неё использует native coding workflow/context и штатный reference fake model.
- `provider-requests.json`: реальные native Anthropic HTTP bodies. API key синтетический, endpoint только loopback. Внешних API-вызовов и пользовательских секретов нет.
- `*-events.json`, `*-profile.toml`, `*-child.toml`, `summary.json`: события, точные config и root responses финального прохода.
- `*-sessions/<fixture-root-name>/`: canonical root/child journals финального прохода; `journal-summary.json` связывает их с case. Более ранние прямые подпапки в этих каталогах оставлены как предыдущие прогоны, финальный источник однозначно указан в summary.
- `verify.py`: пять диагностических PASS, `verify.log`. `verify.py --expect-visible-status`: ожидаемый FAIL на отсутствии timeout в model-visible result, `expected-failure.log`. PASS диагностики не означает исправленный продукт.
- `provenance.json`: hashes готовых binaries. Core binary `09b8d6ef…`, workflow/context и Modules model binary совпадают с ранее проверенными сборками текущих HEAD; заново в этом проходе не компилировались. Reference fake model `0f29aa84…` является штатным тестовым fixture.
- `source-provenance.json`: local/remote HEAD и чистые checkout status. `python3 -m py_compile` для трёх fixture scripts выполнен.

Запуск: `python3 run.py && python3 verify.py`. В scripts используются pinned абсолютные пути к уже собранным binaries; при переносе заменить их доступными сборками тех же SHA.

Полный Rust gate, workflow replay, GUI и live LLM не запускались. Canonical journals сохранены, но это не заявка о replay-эквивалентности. Процессные таймауты, реальный normal tool path, native model serialization и positive/collaboration controls проверены. Сценарии по прежним worktree/GIT_DIR/IDs не повторялись как новые находки.
