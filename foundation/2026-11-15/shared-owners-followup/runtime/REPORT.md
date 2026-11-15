# Core runtime: общий путь доставки в работающий mailbox

## Результат и статус

Найден ограниченный source-only кандидат: `send_message` и running-ветка
`followup_task` используют один private `send_running_message` вместо двух
копий доставки. Один production-файл, **+29/−39 строк, net −10**. Общий путь
охватывает адрес, typed envelope, сохранённого host owner/handle, ошибки и
queued receipt. Это небольшой maintenance cleanup, не крупное архитектурное
упрощение, новое исправление bug или измеренный runtime выигрыш.

**Независимый [source review](REVIEW.md) завершён: blocking source defects
не найдены.** Это reviewed source-only кандидат, не разрешение production
adoption. Rust compilation, rustfmt,
проектные tests, реальные peers, replay, benchmarks и CI **НЕ ЗАПУСКАЛИСЬ**:
Rust/Cargo/rustfmt в текущем окружении отсутствуют. Upstream не изменён.

База: [Core 9437c617](https://github.com/Proteus-harness/Proteus-core/commit/9437c61785cdb5933a980e7d683afb7e85f352e9).
Последующий после базы PR165 commit меняет config/installer, но точные
source identities всё равно проверены на текущем ref, а не перенесены по
названию commit. Пакет содержит 17 проверенных selected source identities,
не полный аудит репозитория.

## Сохраняемая граница

В [message.rs](https://github.com/Proteus-harness/Proteus-core/blob/9437c61785cdb5933a980e7d683afb7e85f352e9/crates/proteus-core/src/core/agent_control/collaboration/message.rs)
два действующих пути последовательно выполняют:

1. Parse нормализованного `running.path`.
2. `AgentControlMessage::from_root`, включая validation и копирование текста.
3. `running.owner.send_agent(&running.handle, message).await`.
4. JSON-проекцию `AgentMessageReceipt`: `Queued`, `turn_started=false`,
   `generation=None` и тот же parsed path.

Helper получает заимствованный `RunningAgent`; ownership остаётся в прежнем
caller. Не добавляются host lookups, locks, retries, spawns, cancellation или
новые state transitions. Единственный backend send остаётся тем же await.
Не делается вывод о размере future, frame-time, allocations или скорости.

| Случай | Сохранённое поведение |
|---|---|
| Недопустимый address | `Err` через прежний `?`, не model-visible ToolResult error |
| Недопустимый envelope | `Ok(tool_error(..., error.to_string()))` |
| Backend send error | `Ok(tool_error(..., format!("{error:#}")))` с полной error chain |
| Успех | Прежний typed receipt и тот же call ID |
| Metadata label | Явные литералы `send_message` / `followup_task`, не `call.name` |
| Lookup/admission | Остаётся разным: `running_agent` и `begin_followup` |
| Idle follow-up | Вся ветка resume/abort/attach/monitor сохранена побайтно |

Последние два различия принципиальны. Общий helper начинается **после**
получения `RunningAgent`; он не объединяет admission и не превращает send в
resume. Исходная гонка завершения после lookup не исправляется и не получает
автоматического повторения или свежего child. Ограничения session ownership,
generation, capacity и resumable history остаются в `control.rs`.

## Проверка дубликатов и отвергнутые объединения

Просмотрены названия PR66–165, описания ближайших опубликованных пакетов и
полный bounded-simplification report PR165. Targeted connector search по `send_message followup_task`,
`RunningAgent` и PR `mailbox` не нашёл аналога этому extraction. Это bounded
проверка, не доказательство полной новизны всего delivery-репозитория.

Не предлагается общий runtime framework ради похожего кода:

- `HookHost` и `ToolHost` на `InvocationOperations` имеют разные gate/error
  semantics и восстановление operation scope. Сведение их к одному body без
  анализа `DelegatingToolHost` изменило бы не только структуру.
- Process cancellation и tool timeout/settlement имеют разные terminal DTO,
  начало/источник cancellation и grace handling. Совпадение `select!` не
  означает одинаковый контракт.
- Insertion-driven history revision остаётся на NaN HOLD из PR165; новый
  helper не касается history, revision или checkpoint.
- Дубли constructors conversation readers и recorder selection невелики;
  отдельный сервис/abstraction для них в этом проходе не оправдан.

Практическая рекомендация: включить этот маленький cleanup в следующий
согласованный bounded пакет после review, а не создавать отдельную крупную
историю о «системном ускорении».

## Выполненная проверка

- Git blob SHA-1 и SHA-256 17 selected files совпали с pinned sources/tree.
- `git apply --check --whitespace=error-all` успешен.
- GNU patch forward/reverse с `--fuzz=0`, без offsets; candidate bytes точно
  совпали с after, reverse восстановил baseline.
- Entire idle-followup branch и `required_message` побайтно не изменились.
- Оба удалённых body совпали с подстановкой helper после удаления whitespace
  и только redundant braces/semicolon одного `return` arm. Call labels
  проверены отдельно. Это текстовое соответствие, **не Rust test**.
- Никакие тесты, contracts, docs upstream или dependency pins не изменены.

Patch SHA-256:
`a43ec06b39a78e1abf8adda2eafc78c332a1c95a0e60b29bfb55909ac234ecde`.

## Что ещё нужно перед adoption

Существующий test
`running_send_and_followup_use_the_child_mailbox_without_spawning` уже
проверяет обе entrypoints, отсутствие второго spawn и доставленные тексты.
`terminal_followup_resumes_same_task_and_keeps_old_completion_immutable`
проверяет отличие idle send от resume. Оба прочитаны на pinned базе, **не
исполнены**. Первый не является полной проверкой envelope/handle/error
matrix: fixture хранит только content. Его следует расширять при выявленной
непокрытой регрессии, а не создавать второй test framework.

Требуется штатный affected collaboration lib target; по agent-control
evidence matrix также реальный peer для адресной доставки/отмены и отдельной
child config. Existing process-pool `fresh_task_expires_facade_history`
проверяет иной lifecycle guard, не служит заменой running-mailbox test.
Пустые GitHub checks не дают CI PASS. Публикация review artifacts сама по
себе не квалифицирует runtime для production.
