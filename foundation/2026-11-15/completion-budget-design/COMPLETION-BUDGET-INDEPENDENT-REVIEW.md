# Независимый bounded review: completion-budget

## Verdict

**HOLD полного record-safe completion delivery исправления поддержан.** В рассмотренных abstractions не найден готовый механизм повторного чтения immutable old-generation report после destructive drain с учётом downstream budget. Это не утверждение невозможности полезного узкого fix. Patch не подготовлен, новая finding не заявляется.

## Причина и доступные границы

WaitAgentTool вызывает drain_completions до serde serialization/json_result и до BoundTools/AfterTool. Drain удаляет до MAX_COMPLETIONS_PER_WAIT записей из VecDeque. json_result помещает весь AgentWaitSnapshot в output String. Hook OutputBudget сплайсит UTF-8-safe head/tail без omission marker и без JSON semantics. Такой splice не доказывает invalid JSON: boundary может оставить синтаксически допустимый документ с полями разных records. Меньшее число records снижает риск, но не обеспечивает integrity одного длинного record.

Core truncate_result действует до AfterTool. finish сначала truncates raw, затем при активных hooks пишет tool_effect_recorded и лишь после вызывает hook. Поэтому этот raw-effect журнал может сохранять pre-hook output, но не полный original batch, если его уже обрезал Core cap. Не следует обещать универсальную восстановимость из «raw» записи. Само наличие journal не является model-visible reread contract данного completion поколения.

ToolContext не передаёт итоговый downstream byte budget; HookResponse::ToolOutput заменяет только String и не сообщает producer ни accepted set, ни delivery acknowledgement. Core cap и опциональные hook cap могут различаться. Fixed 200k drain budget или пропуск output_budget именно для wait_agent не соблюдают произвольную текущую конфигурацию.

AgentRecord.outcome сохраняет latest bounded presentation payload, но attach_followup меняет generation и очищает outcome. QueuedCompletion сохраняет snapshot поколения отдельно до drain. Следовательно, list current agents с include_payload не эквивалентен replay удалённой immutable completion; кроме того, его output снова проходит budget. Child history reference не равен сохранению конкретного report/error/attribution snapshot и может отсутствовать.

## Что можно сделать узко без нового framework

Явный marker вместо необозначенного splice — полезная integrity mitigation: он сообщает, что текст неполон, и не должен выдавать splice за исходный структурированный report. Но это не восстанавливает dequeued reports и не гарантирует delivery identity. Marker нужно вписать в строгий byte budget, включая очень малые configured limits; просто добавить его поверх прежнего head+tail нарушит cap. Marker внутри JSON string также не равен сохранению structured semantics.

Record-aware projection с коротким честным перечнем identity/status может уменьшить misattribution, но должен строиться до произвольного string truncation и сам может не поместиться. Нельзя назвать его полноценным fix без recoverable оригинала или явной политики невозможности доставки. Один report/poll, сокращённые summaries, ToolContent::Json bypass или special hook exemption не решают эту boundary при произвольном cap. JSON bypass особенно не является соблюдением budget.

Наличие ограниченных mitigations означает, что HOLD — решение scope, а не доказанная техническая невозможность любых улучшений. Для полного fix нужны согласованные semantics: сохранить идентичность и recoverable report поколения до подтверждённой доставки/явного discard; дать bounded retrieval/projection с честным indication incomplete; определить, как admission/ack соотносятся с итоговыми caps и конкурентными waiters. Это требования к результату, не предписание новой общей архитектуры. Existing queue/journal можно потенциально использовать, но показанного read/ack контракта для этого сейчас нет. В этом проходе конкретная схема не выбрана и её correctness не доказана.

## Evidence и ограничения

Independently прочитаны WaitAgentTool, json_result, drain/complete/attach_followup/view, ToolContext/HookResponse, BoundTools finish и OutputBudget. Coordinator сообщает 15 blobs, 13 Core code blobs main/pin identical; документация main может отличаться. Historical runtime report не воспроизводился. Вывод об отсутствии reread ограничен представленным collaboration/tool contracts slice, не является exhaustive поиском всего UI и journal tooling.

Самостоятельно пересчитанные SHA256:
- collaboration/mod.rs: eb0b376d31b52e3a84a4a23f83ab0c9b5694537bb734ea4232421bf425c5872d
- collaboration/control.rs: 3d6ab1ce1be021e8205be89ac9ff826bc25a6a2a81b965692b8632e6fdab12d9
- bound_tools/hooks.rs: d3e620e4b5bec30f4b85eb07b59e44f39635de5cae9601edeab486c14fd4a7b2
- hook-pack/lib.rs: 0bab3c53e26f653c64dbfb6144d0c3a21189093347f9a87163586b0bb4648780

Baseline Modules c035142558f0fca43e9772fc0e50ca293abf1531 / Core main bcbda4435534a296c707a1daa250813d692f68e1. Rust/compiler/tests/runtime/project scripts/provider calls/install не запускались. На стадии review production, refs и публикации не менялись; этот docs-only пакет не изменяет production или upstream. Нет compile/runtime/deletion/performance claim.
