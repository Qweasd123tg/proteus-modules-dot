# Completion budget: граница consumption и model-visible delivery

## Итог

**HOLD полного исправления известного completion-budget family.** Новый finding и patch не создавались. Независимое review подтвердило цепочку и отсутствие готового old-generation reread/accepted-set контракта в изученных interfaces. При этом полезные узкие mitigations возможны; HOLD не означает невозможность любого улучшения.

В этом проходе не подменяем целостность delivery косметическим marker и не обходим configured budget через другое поле ToolResult. До выбранного контракта не добавляем новый framework.

## Версии и scope

Начало и конец, 2026-11-15:
- Modules `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core main `bcbda4435534a296c707a1daa250813d692f68e1`.
- Delivery main `c5e0e476dbd988efdc5ddd2bab2b572c979c0c3f`, включая PR117.
- Modules Core pin `41bdfffa6e70228278b4abc758b7f81a12672f35`.

15 source blobs сверены с Git SHA. 13 прочитанных Core code blobs совпадают main/actual pin; runtime-and-events.md взят из main и отличается от pin. PR117 исправляет только HTTP200 context-stop recovery и не закрывает accounting. Этот проход относится к другому уже опубликованному family.

Исторический [исторический completion-budget report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/c5e0e476dbd988efdc5ddd2bab2b572c979c0c3f/research/proteus-continuous-audit-2026-11-13/evidence/completion-budget/REPORT.md) описывает реальную цепочку с opt-in output_budget: шесть completion records были потреблены, а head+tail splice создал valid JSON с хвостом одного агента под identity другого. Старые runtime observations не перезапускались и не выдаются за текущий runtime результат. Это не default Codex failure: исходная основная finding требует включённого hook.

## Подтверждённый текущий source contract

1. `collaboration/control.rs:295–308`: drain удаляет до восьми queued snapshots по count, без aggregate serialized-byte budget.
2. `collaboration/mod.rs:276–307`: wait вызывает drain прежде JSON serialization и возврата ToolResult. `spec.rs:66–80` явно обещает consumption успешного batch; ReadOnly не делает это чтение повторяемым.
3. `bound_tools/hooks.rs:99–118`: Core cap применяется после tool effect, затем при активных hooks записывается ToolEffectRecorded, выполняется AfterTool, и final result снова проходит cap.
4. `hook-pack/src/lib.rs:69–83`: output_budget видит обычную строку и склеивает head/tail без separator и без понимания AgentRecordSnapshot. Это сохраняет byte cap, но не identity границы.
5. `contracts/tool.rs:20–52`: ToolContext не содержит effective downstream output budget. `contracts/hook.rs:99–101,207–209`: ToolOutput заменяет только string; нет accepted-record set, delivery receipt или queue acknowledgement.
6. `domain/tool.rs:149–178`: ToolContent::Json существует, но fallback serializes его после empty output. Перенос туда без согласованного budgeting лишь использовал бы известный structured-content bypass, а не исправлял delivery.

Важно уточнение effect/delivery: raw ToolEffectRecorded находится **после первого Core cap**. Поэтому сохранность полного six-record raw batch из исходного hook сценария нельзя обобщать на Core-cap edge. Child histories могут существовать, но штатный replay payload через wait/list этим не обеспечивается. Безвозвратная потеря всех данных с диска не утверждается.

## Почему latest outcome не является готовым reread

Terminal AgentRecord действительно хранит bounded summary/error, а view умеет include_payload. Но list_agents вызывает view(false). Включить payload не означает восстановить любую ранее consumed generation:

- AgentRecordSnapshot различает path и generation.
- При followup attach `control.rs:431–435` меняет generation и обнуляет latest outcome.
- Старый immutable completion остаётся только в отдельной queue snapshot до drain. Existing test `terminal_followup_resumes_same_task_and_keeps_old_completion_immutable` проверяет именно этот queued generation, не повторное чтение уже drained payload.
- Любой новый list payload сам попадёт под тот же cap/hook.

Требуется сохранять identity и доступность уже **bounded retained payload**, а не обещать восстановление исходного неограниченного child output, который текущий контракт и так ограничивает.

## Рассмотренные узкие варианты

| Вариант | Что реально даёт | Чего не решает |
|---|---|---|
| Явный omission marker между head/tail | Полезная mitigation против незаметного сращивания | Не возвращает consumed records; tiny budgets требуют отдельного поведения |
| Один completion за wait | Уменьшает cross-record splice и оставляет остальные в queue | Single record тоже может превышать budget; меняет batching/число tool round trips |
| Fixed 200k serialized batch до drain | Может защитить конкретный default Core cap | Не учитывает меньший configured Core cap, opt-in hook или последующие transforms |
| list_agents с latest payload | Может перечитать ещё retained latest result | Не сохраняет старые generations и сам подвержен truncation |
| JSON content либо exemption wait_agent из hook | Обходит рассматриваемый splice | Нарушает/обходит выбранный budget, не record-safe budgeting |
| Requeue после ошибки AfterTool | Выглядит как возврат доставки | Tool effect уже settled и raw result может быть записан/виден следующему turn; это не безопасный transactional rollback |

Ни один вариант не признан невозможным как отдельно выбранная mitigation. Здесь нет основания объявлять его полным исправлением integrity + recoverability. Marker-only в частности сознательно не публикуется как очередное поверхностное закрытие family.

## Минимальные требования к дальнейшему решению

Без выбора конкретного framework нужно определить три вещи:
- Единица projection — целый record с неизменной парой path/generation; усечение summary должно быть явным и не заимствовать bytes другого record.
- Какая сторона знает применимый budget до consumption, либо каким versioned способом reread доступен после него. Если даже identity/envelope не помещаются, поведение нельзя молча считать delivery.
- Когда record считается consumed относительно transformations и сохранения effect/result; failure после effect не должен автоматически повторять уже завершённую работу.

Подмена summary byte count serialized JSON length недостаточна из-за escaping и envelope overhead. Контракт хранения/readback должен соблюдать существующие retention bounds и generation transitions. Данный проход не выбирает новое API и не создаёт callback/ack protocol.

## Verification

Перед публикацией повторно проверены текущие refs и Git blob SHA всех 15 исходников по GitHub trees. 13 Core code blobs также сверены с actual pin. Это inert byte/source verification, не выполнение project code.

Независимое заключение: [COMPLETION-BUDGET-INDEPENDENT-REVIEW.md](COMPLETION-BUDGET-INDEPENDENT-REVIEW.md).

Не запускались Rust/cargo/compiler/formatter/tests/project scripts/fixtures/приложение/providers. Ничего не устанавливалось. Этот пакет меняет только документацию delivery repo; production, upstream code, pins и binaries не меняются. Нет patch, runtime PASS, новой finding или measured complexity/performance improvement. Accounting PR117 остаётся открытым.

### Pinned source manifest

| Source | Git blob SHA | Actual Core pin blob |
|---|---|---|
| [crates/proteus-core/src/core/agent_control/collaboration/control.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/agent_control/collaboration/control.rs) | `4e741b9e88893df0d34ecd0fe99977d63b641870` | `4e741b9e88893df0d34ecd0fe99977d63b641870` |
| [crates/proteus-core/src/core/agent_control/collaboration/mod.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/agent_control/collaboration/mod.rs) | `e6740c6bd73084b11222957c75913440a199ca66` | `e6740c6bd73084b11222957c75913440a199ca66` |
| [crates/proteus-core/src/core/bound_tools/hooks.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/bound_tools/hooks.rs) | `3c99fc10fcadc3c7d3d07c79093ce72b7b7ba7d3` | `3c99fc10fcadc3c7d3d07c79093ce72b7b7ba7d3` |
| [crates/proteus-core/src/core/bound_tools/support.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/bound_tools/support.rs) | `1b51f8e1fa2a4367f33fb915deabc11e94d70c1a` | `1b51f8e1fa2a4367f33fb915deabc11e94d70c1a` |
| [crates/proteus-contracts/src/domain/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/domain/tool.rs) | `438e620298bcee1725e8dde6338c69451f3c46a4` | `438e620298bcee1725e8dde6338c69451f3c46a4` |
| [crates/proteus-contracts/src/contracts/hook.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/contracts/hook.rs) | `edd73acbdfa8a601197dc7675d560be1d23525f4` | `edd73acbdfa8a601197dc7675d560be1d23525f4` |
| [crates/proteus-core/src/core/bound_tools.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/bound_tools.rs) | `6cf40ec34828b81d04e4259be851f8c0ba269ff3` | `6cf40ec34828b81d04e4259be851f8c0ba269ff3` |
| [crates/proteus-core/src/core/agent_control/collaboration/spec.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/agent_control/collaboration/spec.rs) | `108947f5eef09a67bacdcb3e230588a4ac2c578e` | `108947f5eef09a67bacdcb3e230588a4ac2c578e` |
| [crates/proteus-contracts/src/contracts/agent_control.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/contracts/agent_control.rs) | `a270d128c785f3d1dd3daa3b49374b953ac6a65b` | `a270d128c785f3d1dd3daa3b49374b953ac6a65b` |
| [crates/proteus-contracts/src/contracts/tool.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/contracts/tool.rs) | `2ad0ec49b7c905e46ec14cb971e13adaadd8163d` | `2ad0ec49b7c905e46ec14cb971e13adaadd8163d` |
| [crates/proteus-core/src/core/agent_control/collaboration/tests.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/agent_control/collaboration/tests.rs) | `28a41406443b84a58cd666873c3ed1997f95760d` | `28a41406443b84a58cd666873c3ed1997f95760d` |
| [crates/proteus-core/tests/process_agent_control/output_limits.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/tests/process_agent_control/output_limits.rs) | `9c99a4cd59e81dfe4ce05de66d9b78e48d85738e` | `9c99a4cd59e81dfe4ce05de66d9b78e48d85738e` |
| [crates/proteus-core/src/core/agent_control/collaboration/message.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/agent_control/collaboration/message.rs) | `57da61056d1975f8626ffdf456f2b7e804a36f64` | `57da61056d1975f8626ffdf456f2b7e804a36f64` |
| [docs/guides/runtime-and-events.md](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/docs/guides/runtime-and-events.md) | `9bebaa1dec95d0d2c758a7ad502eaaadedb882e0` | `9309754b8e47b804f2f570783382f09fc21a23b1` |
| [hook/hook-pack/src/lib.rs](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/hook/hook-pack/src/lib.rs) | `1104288785d0645294816621c8e25e87d4857f70` | n/a |
