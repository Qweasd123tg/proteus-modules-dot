# Независимый source review: TaskTool terminal outcome

## Verdict

В exact candidate source-level blocker не найден. Известный task-terminal-status получает model-visible исход без новой lifecycle abstraction. Это не новая finding и не compile/test/runtime PASS.

Прочитан полный diff четырёх изменённых файлов: task.rs, task/spec.rs, task/tests.rs, runtime-and-events.md. Дополнительно проверены DTO, TaskTool invoke, worktree finalizer, ближайшие BoundTools execution/finish/record/truncation и Modules execution/history append paths.

## Semantics

- Только AgentLifecycleStatus::Completed сохраняет прежние ToolResult::ok, output, suffix ordering и empty-success text_or_status. Другие статусы дают ToolResult::error с полным rendered текстом. Это **Ok(ToolResult { ok: false, ... })** на Rust invoke boundary, а не propagation outer Err, который мог бы обойти обработку результата.
- Текст явно называет observed serialized status и говорит completion was not confirmed, summary may be incomplete, actions may already have taken effect. Starting/Running/Unknown не названы завершившейся ошибкой, отменой или rollback. JSON Value Display намеренно даёт quoted snake_case label; та же Value перемещается в metadata.status. Новый ручной mapping не введён, сравнение Completed корректно покрывает будущие noncompleted variants non_exhaustive enum.
- Summary, optional task_id и workspace_note формируются в прежнем порядке в одном error поле. Поэтому text_or_status error-precedence не скрывает partial summary в оставленном отдельно output. call_id и object metadata сохраняются с прежними canonical overwrite keys tool/status/child_thread_id. Не-object metadata по-прежнему заменяется object; patch не меняет этот существующий fallback.
- Child task resume eligibility и генерация task_id не меняются. Worktree finalize выполняется до formatter и проверяет typed lifecycle status, а не новый ToolResult.ok. Новый текст не обещает, что checkout сохранён/чист или что effects отменены: конкретный note остаётся источником сведений.
- Spec предупреждает об incomplete outcome/effects и предлагает inspect before retrying. Документация согласована с code: successful result только completed, metadata сохраняется, общий budget продолжает действовать.

## Consumers и пределы сохранения

В прочитанных BoundTools invocation/finish/record_result и Modules codex_tools/host/single_loop/plan_execute_review/scaffold/results нет automatic task retry по ToolResult.ok=false. BoundTools записывает/возвращает settled result; scaffold сохраняет его в model/persistent history и сверяет accepted outcome. Это bounded source conclusion, не гарантия всех custom hooks, external UI consumers или последующих решений модели. AfterTool hooks по-прежнему могут преобразовать результат.

BoundTools отдельно обрезает output и error по max_output_bytes. Новый prefix расходует часть того же budget; длинный summary может привести к более раннему усечению task_id/worktree suffix. Formatter tests не доказывают end-to-end сохранение suffix. Статус теперь расположен в начале, но при экстремально малом budget даже полный prefix не гарантирован. Общая truncation policy не расширяется этим patch.

## Compile-shape и proposed tests

Новый import AgentLifecycleStatus существует в contracts; enum Copy/PartialEq/Serialize. Partial moves summary и metadata совместимы с дальнейшим доступом к child_thread_id; status Value читается format! до перемещения в metadata. Existing explicit import enum в tests и super::* не создаёт двух explicit imports. Новых dependencies/API/async state нет.

Прочитаны три новые test functions и усиленный completed test: шесть noncompleted variants с exact error/text_or_status/metadata и suffixes; empty timeout против unchanged empty completed; TaskTool invoke через TimedOutAgentHost возвращает ok=false и partial text без неподтверждённого task_id. Existing completed assertion теперь exact-output. Spec assertion также добавлен. Test host возвращает typed AgentControlResult как реальный boundary, а не изображает transport Err.

Tests не запускались. Нового end-to-end process/worktree/truncation/provider regression здесь нет; worktree note проверяется напрямую formatter fixture. Компиляция и execution assertions не подтверждены.

## Evidence

Coordinator сообщает 26 source blobs и text apply/check/apply-byte equality. Core main baseline bcbda4435534a296c707a1daa250813d692f68e1. Reviewer самостоятельно прочитал exact diff/указанные paths и пересчитал SHA256:

- patch: 08162769a69d508c78feed848437129e3492ed13ca2d39eedffa24842f64c8cf
- task.rs: 552e262f232a7352176f07ef21288afbeaa4ccb7635647bf4026a6c9d93b7fb0
- task/spec.rs: d74d02f1bb25be1c969a4a731700b9cfed8f663661eeb74ca26f0781cea26c3a
- task/tests.rs: 471e9b41c65cdefb2f0366dab068335dbdadb69d551a6bf6028dd5eb2e987de9
- runtime-and-events.md: f341bb79fa567317b004126929148b62e0824338398a1a97501451c57648763d

Rust/compiler/tests/runtime/project scripts/dependencies не запускались. Production, refs и публикации не менялись. Патч Core не означает автоматическое обновление pinned consumers или подтверждённый rollout.
